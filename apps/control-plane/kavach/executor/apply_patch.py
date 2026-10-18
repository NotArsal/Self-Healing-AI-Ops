"""`apply_patch` — the one action whose content a model wrote.

Everything else in the catalogue picks a name from a closed list and writes
a value that was recorded earlier. This writes prose a language model
produced, which is why `PRD.md` §12 calls it the highest-risk thing in the
system and why it is the last thing built.

THE TRIAL HAPPENS IN `prepare()`, AND THAT IS THE WHOLE DESIGN
`ARCHITECTURE.md` §6.2.1 constraint 4: *"Sandbox is mandatory, not routed.
The patch applies to a cloned stack first and fast verification runs there.
No sandbox result, no proposal."*

So by the time `permit()` sees this action, the patch has already been
applied to an isolated clone of the target and the clone's fast set has
answered. `prepare()` does the generating, the checking and the trial;
`execute()` only replays, against production, a change that has already
been shown to work somewhere survivable. An action whose trial failed never
reaches `execute()` because it never passes the gate.

That ordering is unusual - most actions capture a witness in `prepare()`
and do the work in `execute()` - and it is deliberate. A HIGH-tier
generated write has to be provably safe BEFORE a human is asked to approve
it, or the approval is a rubber stamp on an untested diff.

THE INVERSE IS BYTES, NOT A MODEL CALL
§6.0: *"The inverse is deterministic data, never a model call... Capture
the pre-state witness; do not re-derive it."* `prepare()` records the exact
prior contents of the file, and `invert()` writes them back. The same
machinery `rollback_prompt` already proves live, with the content authored
instead of recalled.

WHAT IS NOT HERE
No shell, no command string, no `exec` adapter. The model emits diff TEXT;
`executor/adapters/git.py` applies it and is the only thing that runs
`git`, with no commit or push code path in it at all. `FR-27` is unchanged.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kavach.executor import patch_checks, sandbox
from kavach.executor.adapters import git
from kavach.executor.config_rollback import ActionError, idempotency_key
from kavach.rca.patch_engine import PatchResult
from kavach.target import TargetClient, TargetError

ACTION_NAME = "apply_patch"
# Constraint 1: fixed by the action, never computed from its parameters. A
# model-authored payload is HIGH whatever it claims to touch.
RISK_TIER = patch_checks.RISK_TIER

# `-p2`, not the conventional `-p1`, and the fence depends on it.
#
# A diff path is `a/prompts/answer.txt`. `-p1` strips `a/`, leaving
# `prompts/answer.txt`, which has to be rooted at the directory CONTAINING
# prompts/ - the target repository root for production, which would make the
# whole target writable by a model-authored diff. `-p2` strips `a/prompts/`
# and roots the patch at the prompts directory itself.
#
# So the git fence and ADR 0008's "prompts are the only writable path into
# the target" become the same sentence, in both production and the sandbox,
# which do not even share a directory layout. `patch_checks.check_paths` has
# already refused anything not under a declared versioned path, so a diff
# reaching here always has the `prompts/` component to strip.
STRIP = 2


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


@dataclass
class SandboxTrial:
    """What happened when the patch was tried on a clone."""

    ran: bool = False
    applied: bool = False
    pass_rate: float | None = None
    passed: bool | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ran": self.ran, "applied": self.applied,
                "pass_rate": self.pass_rate, "passed": self.passed,
                "detail": self.detail}


@dataclass
class ApplyPatch:
    """A generated patch to one declared file, tried on a clone first."""

    incident_id: str
    proposal_diff: str
    target_file: str                     # repo-relative, e.g. prompts/answer.txt
    prompts_dir: Path                 # where the real file lives
    name: str = ACTION_NAME
    risk_tier: str = RISK_TIER

    # The same three inputs the proposal was checked against, carried so the
    # FULL gate can re-run here with a sandbox result in hand. Re-checking
    # rather than trusting the proposal's verdict is the point: the static
    # five were answerable before the trial, the sixth was not.
    versioned_paths: dict[str, str] = field(default_factory=dict)
    denied_mutations: list[str] = field(default_factory=list)
    witness: dict[str, str] = field(default_factory=dict)

    pre_state: dict[str, Any] = field(default_factory=dict)
    inverse_text: dict[str, str] = field(default_factory=dict)
    trial: SandboxTrial = field(default_factory=SandboxTrial)
    verdict_reasons: list[str] = field(default_factory=list)
    rationale: str = ""
    idem_key: str = ""

    executed: bool = False
    reverted: bool = False
    error: str = ""
    prepared_at: str = ""
    executed_at: str = ""

    # `loop.py` reads these off the action by duck typing to build its
    # ActionRequest. Digests, never the prose: a decision record carrying a
    # model's full diff would be unreadable, and the digest is what a human
    # can check the applied file against.
    @property
    def target_settings(self) -> dict[str, Any]:
        return {self.target_file: digest(self.proposal_diff)}

    @property
    def inverse_settings(self) -> dict[str, Any]:
        return {k: digest(v) for k, v in self.inverse_text.items()}

    @property
    def sandbox_passed(self) -> bool | None:
        """Has a clone already run this patch and agreed?

        Read by `loop.py` when `permit()` returns REQUIRE_SANDBOX. That
        verdict means "no production write until a clone agrees", and for
        this action the clone ran during `prepare()` - constraint 4 makes
        the sandbox a precondition of the proposal, not a later stage.

        An action without this attribute reads as None and the loop waits,
        which is every other action in the catalogue.
        """
        return self.trial.passed

    # --- preparation: generate, check, and TRY IT ON A CLONE ---------------

    def prepare(self, client: TargetClient) -> None:
        """Capture the witness, then prove the patch works on a clone.

        Raises rather than returning a failed action. `executor/base.py`
        makes an action without a working inverse unrepresentable; the same
        reasoning says an unproven generated write should not become an
        object the rest of the loop can hold.
        """
        prod = self.prompts_dir / Path(self.target_file).name
        if not prod.is_file():
            raise ActionError(
                f"no file at {prod}; the patch names {self.target_file!r} "
                f"but production does not have it"
            )
        before = prod.read_text(encoding="utf-8")
        self.inverse_text = {self.target_file: before}

        try:
            cfg = client.config()
        except TargetError as exc:
            raise ActionError(f"cannot read the target: {exc}") from exc
        self.pre_state = {
            "prompt_version": cfg.get("prompt_version", {}),
            "config_hash": cfg.get("config_hash", ""),
            "file": self.target_file,
            "digest_before": digest(before),
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self.idem_key = idempotency_key(
            self.incident_id, self.name, self.target_settings)

        self._run_trial()
        if not self.trial.passed:
            # Refused here rather than left to the gate below, which would
            # also catch it: the gate can only say "no sandbox result", while
            # `trial.detail` holds the reason - docker down, the patch not
            # applying to the clone, the fast set failing. Those need
            # different responses from a human, so they must not collapse
            # into one message.
            raise ActionError(
                f"the patch did not pass in the sandbox, so it does not "
                f"reach production: {self.trial.detail}. This is constraint "
                f"4 doing its job, not a failure of the loop"
            )

        # NOW the sixth check has an answer, so the full gate runs. Until
        # this moment `evaluate` could only ever have denied - which is the
        # bug 3c was split to fix, and re-running the static five here with
        # the sandbox result is what makes the split honest rather than a
        # way of skipping a check.
        verdict = patch_checks.evaluate(
            diff=self.proposal_diff,
            versioned_paths=self.versioned_paths,
            denied_mutations=self.denied_mutations,
            witness=self.witness,
            sandbox_passed=self.trial.passed,
        )
        self.verdict_reasons = list(verdict.reasons)
        if not verdict.allowed:
            raise ActionError(
                f"the full gate refused this patch after its sandbox run: "
                f"{verdict.reasons}"
            )
        self.prepared_at = datetime.now(UTC).isoformat(timespec="seconds")

    def _run_trial(self) -> None:
        """Apply to the clone, verify there, then put the clone back.

        The clone is restored whatever happens: a sandbox carrying one
        incident's experiment into the next one's verification is the
        contamination this project has been bitten by repeatedly, and the
        sandbox is the one place where it would be invisible.
        """
        from kavach.verification import fast  # local: host-side only

        state = sandbox.ensure()
        if not state.usable:
            self.trial.detail = (
                f"no usable sandbox, so the patch cannot be tried: "
                f"{state.problems}"
            )
            return
        self.trial.ran = True

        area = sandbox.prompts_dir()
        name = Path(self.target_file).name
        sandbox_file = area / name
        restore = (sandbox_file.read_text(encoding="utf-8")
                   if sandbox_file.is_file() else None)

        # The clone must start from what production actually holds, or the
        # trial answers a question about the wrong file. Nothing in `seed()`
        # copies prompts - the two directories matching is luck, not a
        # guarantee - so the one file under test is synced here explicitly.
        sandbox_file.write_text(self.inverse_text[self.target_file],
                                encoding="utf-8", newline="")
        try:
            git.apply(self.proposal_diff, area, area, strip=STRIP)
            self.trial.applied = True
        except git.GitAdapterError as exc:
            self.trial.detail = f"patch did not apply in the sandbox: {exc}"
            return

        try:
            sandbox_client = TargetClient(sandbox.endpoints())
            result = fast.run(sandbox_client, _fast_set_path(),
                              check_health=True)
            self.trial.pass_rate = result.pass_rate
            self.trial.passed = result.passed
            self.trial.detail = (
                f"sandbox fast set {result.pass_rate:.0%} "
                f"({'pass' if result.passed else 'fail'})"
            )
        except Exception as exc:
            self.trial.passed = False
            self.trial.detail = f"sandbox verification failed to run: {exc}"
        finally:
            if restore is not None:
                sandbox_file.write_text(restore, encoding="utf-8", newline="")

    # --- execution ---------------------------------------------------------

    def execute(self, _client: TargetClient) -> None:
        """Replay, against production, a change already proven on a clone."""
        if not self.prepared_at:
            raise ActionError(
                "prepare() must run before execute(): without it there is no "
                "witness, no inverse and no sandbox result")
        if self.executed:
            return
        if not self.trial.passed:
            raise ActionError(
                "refusing to execute a patch with no passing sandbox trial")
        try:
            # Re-checked against production as it stands NOW, not as it stood
            # when the proposal was made. A human may have edited the file
            # while the approval sat waiting.
            git.apply(self.proposal_diff, self.prompts_dir,
                      self.prompts_dir, strip=STRIP)
        except git.GitAdapterError as exc:
            self.error = str(exc)
            raise ActionError(
                f"{self.name} failed against production: {exc}. If the file "
                f"moved since the witness was taken, escalating is correct"
            ) from exc
        self.executed = True
        self.executed_at = datetime.now(UTC).isoformat(timespec="seconds")

    def invert(self, _client: TargetClient) -> None:
        """Write back the exact prior bytes. Deterministic data, never a model."""
        if not self.inverse_text:
            raise ActionError("no inverse recorded; nothing can be restored")
        for name, text in self.inverse_text.items():
            path = self.prompts_dir / Path(name).name
            path.write_text(text, encoding="utf-8", newline="")
        self.reverted = True

    # --- verification ------------------------------------------------------

    def _live_digests(self, client: TargetClient) -> dict[str, str]:
        cfg = client.config()
        return dict((cfg.get("prompt_version") or {}).get("files") or {})

    def verify_applied(self, client: TargetClient) -> tuple[bool, str]:
        """Does the RUNNING target now serve the patched file?

        Asked of the target, never of the filesystem: re-reading the file
        this action just wrote proves only that the write happened, which is
        never the thing in doubt.
        """
        name = Path(self.target_file).name
        want = digest((self.prompts_dir / name).read_text(encoding="utf-8"))
        try:
            live = self._live_digests(client).get(name)
        except TargetError as exc:
            return False, f"cannot read the target's prompt version: {exc}"
        if live != want:
            return False, (f"the target reports {live} for {name}, not the "
                           f"patched {want}")
        return True, f"the target serves the patched {name} ({want})"

    def verify_restored(self, client: TargetClient) -> tuple[bool, str]:
        name = Path(self.target_file).name
        want = digest(self.inverse_text[self.target_file])
        try:
            live = self._live_digests(client).get(name)
        except TargetError as exc:
            return False, f"cannot read the target: {exc}"
        if live != want:
            return False, f"not restored: target reports {live}, witness {want}"
        return True, "the target reports the pre-state witness"

    def unchanged_elsewhere(self, client: TargetClient) -> tuple[bool, str]:
        try:
            cfg = client.config()
        except TargetError as exc:
            return False, f"cannot read the target: {exc}"
        live = dict((cfg.get("prompt_version") or {}).get("files") or {})
        before = dict((self.pre_state.get("prompt_version") or {}).get("files") or {})
        touched = {Path(self.target_file).name}
        drift = {n: (before.get(n), live.get(n)) for n in set(before) | set(live)
                 if n not in touched and live.get(n) != before.get(n)}
        if drift:
            return False, f"untouched files changed: {drift}"
        was = str(self.pre_state.get("config_hash") or "")
        now = str(cfg.get("config_hash") or "")
        if was and now and was != now:
            return False, f"config_hash moved {was} -> {now} during a file-only repair"
        return True, "nothing outside the patched file changed"

    # --- record -------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Digests and the rationale. The diff itself goes in the record too,
        because a generated write that cannot be read back is not auditable -
        but it is the ONE action where that is true, and it is bounded by the
        diff budget to at most a few dozen lines."""
        return {
            "incident_id": self.incident_id,
            "action": self.name,
            "risk_tier": self.risk_tier,
            "idempotency_key": self.idem_key,
            "target_file": self.target_file,
            "requested_settings": self.target_settings,
            "inverse_settings": self.inverse_settings,
            "rationale": self.rationale,
            "diff": self.proposal_diff,
            "sandbox_trial": self.trial.to_dict(),
            "verdict_reasons": self.verdict_reasons,
            "pre_state": self.pre_state,
            "executed": self.executed,
            "reverted": self.reverted,
            "prepared_at": self.prepared_at,
            "executed_at": self.executed_at,
            "error": self.error,
        }


def _fast_set_path() -> Path:
    """Resolved by `fast.resolve_set`, as `api/runner.py` does it."""
    from kavach.verification import fast

    root = Path(__file__).resolve().parents[2]
    found = fast.resolve_set("kavach/verification/fast_set.yaml", root)
    if found is None:
        raise ActionError(f"fast verification set not found under {root}")
    return found


def build_from_proposal(
    incident_id: str,
    client: TargetClient,
    result: PatchResult,
    prompts_dir: Path,
    versioned_paths: dict[str, str],
    denied_mutations: list[str],
    witness: dict[str, str],
) -> ApplyPatch:
    """Construct the action from a vetted proposal.

    Refuses anything the proposal stage already refused. The checks are not
    re-run here for a different answer - they are re-asserted so that a
    caller cannot assemble an action out of a rejected proposal by mistake.
    """
    if result.proposal is None:
        raise ActionError(f"no patch was produced: {result.error or 'unknown'}")
    if not result.usable:
        raise ActionError(
            f"refusing to build an action from a proposal that did not pass "
            f"its checks: {result.reasons}"
        )
    action = ApplyPatch(
        incident_id=incident_id,
        proposal_diff=result.proposal.diff,
        target_file=result.proposal.target_path,
        prompts_dir=prompts_dir,
        rationale=result.proposal.rationale,
        versioned_paths=versioned_paths,
        denied_mutations=denied_mutations,
        witness=witness,
    )
    action.prepare(client)
    return action
