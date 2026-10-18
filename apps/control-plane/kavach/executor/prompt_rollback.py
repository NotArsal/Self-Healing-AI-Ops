"""`rollback_prompt` — restore prompt files to their captured known-good text.

THE FIRST ACTION IN THIS SYSTEM THAT WRITES A FILE, AND WHY THAT IS NOT A SHELL
Every action before this one wrote through the target's validated HTTP config
interface. Prompts are not settable there: `control_interface.settable` lists
six scalar keys, and the target exposes no endpoint that returns or accepts
prompt text. Adding one would be a twelfth permitted addition to the target
(`PRD.md` §5.2 allows eleven), so the write goes to the bind-mounted directory
the target reads from.

That is still not arbitrary execution (`FR-27`). There is no command string,
no shell, and no path into this module from a model: the filenames come from
the TARGET's own `prompt_version.files` report, every one is re-validated here
against the resolved prompts directory, and the bytes come from the baseline
capture on disk. A model can propose `rollback_prompt`; it cannot propose what
to write or where.

WHY NO RESTART, AND WHY THAT IS LOAD-BEARING
The target's `prompts_loader` reads each prompt per request with no cache,
deliberately, so that a revert "takes effect without a rebuild or restart". A
repair that needed a container restart would be a `docker restart` wearing a
prompt's clothes, with a restart's blast radius. This writes two files and the
next request uses them.

THE INVERSE IS THE BYTES THAT WERE THERE, NOT THE BASELINE
`prepare()` reads the current file contents and records them. If the repair is
unwound, the target goes back to the degraded prompt — which is correct, and
is the same stance `ConfigRollback` takes. An inverse that restored the
baseline instead would be a second repair pretending to be an undo, and would
make a failed verification unobservable.

VERIFICATION ASKS THE TARGET, NOT THE FILESYSTEM
`verify_applied` compares against `client.config()["prompt_version"]`, the
digests the RUNNING backend computes from the directory it is actually
reading. Re-hashing the file this action just wrote would only prove the write
succeeded, which is never the thing in doubt; what is in doubt is whether the
backend sees it, and only the backend can answer that.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kavach.executor.config_rollback import ActionError, idempotency_key
from kavach.target import TargetClient, TargetError

ACTION_NAME = "rollback_prompt"
# MEDIUM, on the same reasoning as `rollback_config`: it changes application
# behaviour and is reversible from a recorded witness. Not LOW — a prompt is
# the instruction the model follows, so this moves answer quality directly,
# which is the line ARCHITECTURE.md §6.2 draws between LOW and MEDIUM.
RISK_TIER = "MEDIUM"

# A prompt file is a flat `*.txt` name in one directory. Anything else is
# refused rather than normalised: this is the only place in Kavach where a
# name becomes a filesystem path, so it is a trust boundary even though both
# sides of it are currently trusted.
SUFFIX = ".txt"


def digest(text: str) -> str:
    """The same digest the target computes, so the two can be compared."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def resolve(prompts_dir: Path, name: str) -> Path:
    """Map a reported prompt name to a path inside `prompts_dir`, or refuse."""
    if not name or name != Path(name).name or name in (".", ".."):
        raise ActionError(
            f"refusing a prompt name that is not a bare filename: {name!r}"
        )
    if not name.endswith(SUFFIX):
        raise ActionError(
            f"refusing a prompt name that is not a {SUFFIX} file: {name!r}"
        )
    root = prompts_dir.resolve()
    path = (root / name).resolve()
    # Belt and braces after the basename check: a symlink inside the directory
    # would still resolve outside it.
    if path.parent != root:
        raise ActionError(
            f"refusing to write outside {root}: {name!r} resolves to {path}"
        )
    return path


@dataclass
class PromptRollback:
    """A restore of specific prompt files, with its inverse captured up front."""

    incident_id: str
    prompts_dir: Path
    # name -> the known-good text to write. Narrowed in prepare() to the files
    # that are not already at that text.
    target_prompts: dict[str, str] = field(default_factory=dict)
    name: str = ACTION_NAME
    risk_tier: str = RISK_TIER

    pre_state: dict[str, Any] = field(default_factory=dict)
    # The bytes that were there before the write.
    inverse_prompts: dict[str, str] = field(default_factory=dict)
    idem_key: str = ""

    executed: bool = False
    reverted: bool = False
    error: str = ""
    prepared_at: str = ""
    executed_at: str = ""

    # `permit()` reads these two off the action by duck typing (`loop.py`), so
    # an action without them would reach the gate showing no parameters and no
    # inverse, and a sound repair would be denied for failing a check it
    # actually passes.
    @property
    def target_settings(self) -> dict[str, Any]:
        """What the gate sees as this action's parameters: names and digests,
        never the prompt text. The deny-list matches on parameter names, and a
        multi-kilobyte value in a decision record helps nobody."""
        return {n: digest(t) for n, t in self.target_prompts.items()}

    @property
    def inverse_settings(self) -> dict[str, Any]:
        return {n: digest(t) for n, t in self.inverse_prompts.items()}

    # --- preparation --------------------------------------------------------

    def prepare(self, client: TargetClient) -> None:
        """Capture the witness and derive the inverse. No writes."""
        if not self.target_prompts:
            raise ActionError(
                "no known-good prompt text was supplied, so there is nothing "
                "to restore. A rollback with no recorded target is a guess"
            )
        try:
            cfg = client.config()
        except TargetError as exc:
            raise ActionError(
                f"cannot read the target's prompt version: {exc}"
            ) from exc
        reported = dict((cfg.get("prompt_version") or {}).get("files") or {})

        current: dict[str, str] = {}
        needed: dict[str, str] = {}
        for name, want in self.target_prompts.items():
            path = resolve(self.prompts_dir, name)
            if not path.is_file():
                raise ActionError(
                    f"the baseline holds known-good text for {name} but there "
                    f"is no such file at {path}; the control plane is not "
                    f"looking at the directory the target reads"
                )
            if name not in reported:
                raise ActionError(
                    f"the target does not report a prompt named {name}, so a "
                    f"write to {path} could not be verified against it"
                )
            live = path.read_text(encoding="utf-8")
            if digest(live) != reported[name]:
                raise ActionError(
                    f"{path} hashes to {digest(live)} but the target reports "
                    f"{reported[name]} for {name}; these are different files, "
                    f"and writing this one would repair nothing"
                )
            current[name] = live
            # Already correct: writing identical bytes is a no-op that still
            # moves an mtime and still widens `unchanged_elsewhere`'s scope.
            if live != want:
                needed[name] = want

        if not needed:
            raise ActionError(
                "every prompt already matches its captured known-good text, "
                "so this repair would write nothing. A no-op reported as a "
                "successful repair is a false recovery"
            )

        self.target_prompts = needed
        self.inverse_prompts = {n: current[n] for n in needed}
        self.pre_state = {
            "prompt_version": cfg.get("prompt_version", {}),
            "config_hash": cfg.get("config_hash", ""),
            "prompts_dir": str(self.prompts_dir),
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self.idem_key = idempotency_key(
            self.incident_id, self.name, self.target_settings
        )
        self.prepared_at = datetime.now(UTC).isoformat(timespec="seconds")

    # --- execution ----------------------------------------------------------

    def _write(self, texts: dict[str, str]) -> None:
        for name, text in texts.items():
            path = resolve(self.prompts_dir, name)
            # Written in place rather than atomically by rename: the target
            # reads this directory through a bind mount, where a rename is not
            # guaranteed to be visible as one operation. A torn read would be a
            # one-request wobble in a file of a few hundred bytes; a rename
            # that silently did not land would be a repair that reported
            # success and changed nothing.
            #
            # `newline=""` IS LOAD-BEARING, and only on Windows. Without it
            # Python translates every `\n` to `\r\n` on write, so restoring a
            # prompt captured from an LF file would produce a CRLF file with
            # different bytes and therefore a different digest. The repair
            # would then write "the known-good text" and `verify_applied`
            # would correctly report that the target does not hash to the
            # known-good - a repair that fails on a line-ending convention.
            # The target's prompts are LF; this keeps whatever they are.
            path.write_text(text, encoding="utf-8", newline="")

    def execute(self, _client: TargetClient) -> None:
        # `_client`: the Action protocol passes it to every method, and a
        # filesystem write does not need it. Verification does, and takes it.
        if not self.prepared_at:
            raise ActionError("prepare() must run before execute(): without a "
                              "pre-state witness there is no inverse")
        if self.executed:
            # Idempotent by the same key: a duplicate is a no-op, not a second
            # write.
            return
        try:
            self._write(self.target_prompts)
        except OSError as exc:
            self.error = str(exc)
            raise ActionError(f"{self.name} failed: {exc}") from exc
        self.executed = True
        self.executed_at = datetime.now(UTC).isoformat(timespec="seconds")

    def invert(self, _client: TargetClient) -> None:
        """Rewrite the bytes that were there before. Deterministic data."""
        if not self.inverse_prompts:
            raise ActionError("no inverse recorded; nothing can be restored")
        try:
            self._write(self.inverse_prompts)
        except OSError as exc:
            self.error = str(exc)
            raise ActionError(f"inverse of {self.name} failed: {exc}") from exc
        self.reverted = True

    # --- verification -------------------------------------------------------

    def _compare(
        self, client: TargetClient, want: dict[str, str], label: str,
    ) -> tuple[bool, str]:
        try:
            cfg = client.config()
        except TargetError as exc:
            return False, f"cannot read the target's prompt version: {exc}"
        live = dict((cfg.get("prompt_version") or {}).get("files") or {})
        bad = {n: {label: digest(t), "target_reports": live.get(n)}
               for n, t in want.items() if live.get(n) != digest(t)}
        if bad:
            return False, f"prompts do not match the {label}: {bad}"
        return True, (f"the target reports digests matching the {label} for "
                      f"{sorted(want)}")

    def verify_applied(self, client: TargetClient) -> tuple[bool, str]:
        """Does the RUNNING target now hash these prompts to the known-good?"""
        return self._compare(client, self.target_prompts, "known-good")

    def verify_restored(self, client: TargetClient) -> tuple[bool, str]:
        """After invert(), is the pre-state text back?"""
        return self._compare(client, self.inverse_prompts, "pre-state witness")

    def unchanged_elsewhere(self, client: TargetClient) -> tuple[bool, str]:
        """Did a prompt outside this action's scope, or any setting, move?"""
        try:
            cfg = client.config()
        except TargetError as exc:
            return False, f"cannot read the target config: {exc}"
        live = dict((cfg.get("prompt_version") or {}).get("files") or {})
        before = dict((self.pre_state.get("prompt_version") or {}).get("files") or {})
        touched = set(self.target_prompts)
        drift = {n: (before.get(n), live.get(n))
                 for n in set(before) | set(live)
                 if n not in touched and live.get(n) != before.get(n)}
        if drift:
            return False, f"untouched prompt files changed: {drift}"
        # A prompt write must not move runtime config. If it has, something
        # other than this action wrote to the target during the repair.
        was = str(self.pre_state.get("config_hash") or "")
        now = str(cfg.get("config_hash") or "")
        if was and now and was != now:
            return False, (f"the target's config_hash moved {was} -> {now} "
                           f"during a prompt-only repair")
        return True, ("no prompt outside the rollback scope changed, and "
                      "config_hash held")

    # --- record -------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Digests and sizes, never prompt text: the audit log is append-only
        and a full prompt in every record would make it unreadable."""
        return {
            "incident_id": self.incident_id,
            "action": self.name,
            "risk_tier": self.risk_tier,
            "idempotency_key": self.idem_key,
            "prompts_dir": str(self.prompts_dir),
            "requested_settings": self.target_settings,
            "inverse_settings": self.inverse_settings,
            "restored_files": sorted(self.target_prompts),
            "bytes_written": {n: len(t.encode())
                              for n, t in self.target_prompts.items()},
            "pre_state": self.pre_state,
            "executed": self.executed,
            "reverted": self.reverted,
            "prepared_at": self.prepared_at,
            "executed_at": self.executed_at,
            "error": self.error,
        }


def build_rollback_for_prompt_regression(
    incident_id: str,
    client: TargetClient,
    known_good: dict[str, Any] | None = None,
) -> PromptRollback:
    """Construct a `rollback_prompt` repair.

    `known_good` is `{"dir": <prompts directory>, "files": {name: text}}`, as
    `api/runner.py`'s `repair_values()` assembles it from the manifest's
    `versioned_paths.prompts` and the baseline capture's `prompt_contents`.

    It arrives through `repair_values` rather than through the detector's
    `repair_target` on purpose. `loop.py` reserves `repair_target` for a value
    that ONLY detection can know — F08's drifted settings are the case it was
    added for — and the known-good prompt text is not that: it is on disk in
    the baseline, and the directory is declared in the manifest. Routing it
    through the channel already declared for manifest-derived repair values
    keeps the detector free of filesystem knowledge.

    Signature mirrors the other builders so the registry can build any action
    by name with the same call shape.
    """
    if not known_good:
        raise ActionError(
            "no captured prompt text is available, so there is nothing to "
            "roll back TO. Re-run `make onboard`: a baseline captured before "
            "`prompt_contents` existed records digests only, and a digest "
            "restores nothing"
        )
    files = {str(k): str(v) for k, v in (known_good.get("files") or {}).items()}
    directory = known_good.get("dir")
    if not files:
        raise ActionError(
            "the baseline capture holds no prompt text. A rollback that writes "
            "nothing must not be reported as a repair"
        )
    if not directory:
        raise ActionError(
            "no prompts directory is declared for this project "
            "(`versioned_paths.prompts` in its manifest), so there is nowhere "
            "to write. A guessed path would be a write into the dark"
        )

    action = PromptRollback(
        incident_id=incident_id,
        prompts_dir=Path(str(directory)),
        target_prompts=files,
    )
    action.prepare(client)
    return action
