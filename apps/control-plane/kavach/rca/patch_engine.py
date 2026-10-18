"""Asking the model for a repair, and refusing to trust any of it.

This is the only place in Kavach where a model's output becomes content
rather than a choice from a closed list. `PRD.md` §12 calls it "the highest
risk thing in the system", so this module's job is to produce a PROPOSAL
and nothing more: it writes no file, runs no git, touches no container, and
returns a verdict that is already attached to the reasons it might be
refused.

THE SEQUENCE, AND WHY IT IS THIS WAY ROUND
    1. narrow what the model can even say   (enum of declared files)
    2. ask                                   (schema-constrained decode)
    3. check deterministically               (`patch_checks.evaluate`)
    4. check it still fits the file          (`git apply --check`)

Steps 3 and 4 are different questions. Step 3 asks "is this patch
permitted" - the right path, inside budget, no denied content, an inverse
exists. Step 4 asks "does this patch still apply" - whether the file has
moved since the witness. A patch can pass either and fail the other, and
both have to hold.

Neither step is the sandbox. `patch_checks.check_sandbox_result` refuses a
proposal whose sandbox result is `None`, so nothing produced here can be
applied to the running system on the strength of these checks alone.

WHAT THIS MODULE WILL NOT DO
It will not retry a refused patch with a nudged prompt. A model that
produced a patch touching `backend/db.py` is not one re-prompting makes
trustworthy for this incident, and a retry loop around a HIGH-tier
generated write is how "bounded" quietly stops being true. One attempt,
recorded with its verdict, and a human sees the result either way.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kavach.executor import patch_checks
from kavach.executor.adapters import git
from kavach.llm.client import LlmError, OllamaClient
from kavach.rca.patch_schema import PatchProposal, ollama_schema

PROMPT = Path(__file__).resolve().parents[1] / "llm" / "prompts" / "patch.txt"


@dataclass
class PatchResult:
    """A proposal and everything known about whether it may be used."""

    proposal: PatchProposal | None = None
    verdict: patch_checks.PatchVerdict | None = None
    applies_cleanly: bool | None = None
    latency_s: float = 0.0
    error: str = ""
    raw: str = ""
    reasons: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """Deliberately NOT "the model answered". A proposal is usable only
        when it is permitted AND still fits the file - and even then only as
        input to a sandbox run, never as grounds to write production."""
        return bool(
            self.proposal is not None
            and self.verdict is not None
            and self.verdict.allowed
            and self.applies_cleanly
        )


def build_prompt(
    diagnosis: dict[str, Any],
    evidence: str,
    target_path: str,
    file_contents: str,
    prompt_path: Path | None = None,
) -> str:
    template = (prompt_path or PROMPT).read_text(encoding="utf-8")
    return (template
            .replace("{diagnosis}", json.dumps(diagnosis, indent=2)[:1500])
            .replace("{evidence}", evidence[:3000])
            .replace("{target_path}", target_path)
            .replace("{file_contents}", file_contents[:3000]))


def propose(
    *,
    llm: OllamaClient,
    diagnosis: dict[str, Any],
    evidence: str,
    target_path: str,
    file_contents: str,
    versioned_paths: dict[str, str],
    denied_mutations: list[str],
    witness: dict[str, str],
    patch_root: Path,
    boundary: Path,
    declared_files: list[str] | None = None,
) -> PatchResult:
    """Ask for one patch and return it with its verdict already attached.

    `sandbox_passed` is deliberately not a parameter: no sandbox has run
    yet, which is why this calls `evaluate_static` and why `usable` means
    "worth trying in a sandbox", never "safe to apply to production". The
    full six-check `evaluate` runs later, with a real sandbox result.
    """
    result = PatchResult()
    files = declared_files or sorted(witness)
    t0 = time.perf_counter()
    try:
        schema = ollama_schema(files)
        prompt = build_prompt(diagnosis, evidence, target_path, file_contents)
        reply = llm.structured(
            system="You propose one small, reversible edit to one text file.",
            user=prompt,
            schema=schema,
        )
        result.raw = reply.raw[:2000]
        result.proposal = PatchProposal.model_validate(reply.parsed())
    except (LlmError, ValueError) as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        return result
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        return result
    finally:
        result.latency_s = round(time.perf_counter() - t0, 2)

    # 3. Is it permitted? The FIVE checks answerable now. Not the sixth:
    # constraint 4 asks what happened in the sandbox, and no sandbox has
    # run at proposal time. Calling the full gate here denied every
    # proposal and so prevented the applicability test from ever running -
    # the sandbox check was gating the road to the sandbox.
    verdict = patch_checks.evaluate_static(
        diff=result.proposal.diff,
        versioned_paths=versioned_paths,
        denied_mutations=denied_mutations,
        witness=witness,
    )
    result.verdict = verdict

    # A model that named a path outside the enum it was given is a bigger
    # problem than a refused patch, so it is called out rather than folded
    # into the generic path refusal.
    if result.proposal.target_path not in files:
        verdict.deny(
            f"the model returned target_path {result.proposal.target_path!r}, "
            f"which was not in the enum it was constrained to ({files}). The "
            f"decoder constraint did not hold"
        )

    # 4. Does it still fit the file? Only asked when it is permitted: there
    # is no point testing whether a forbidden patch applies, and running
    # `git apply --check` on unvetted content is work for nothing.
    if verdict.allowed:
        try:
            git.check(result.proposal.diff, patch_root, boundary)
            result.applies_cleanly = True
        except git.GitAdapterError as exc:
            result.applies_cleanly = False
            verdict.deny(
                f"the patch does not apply to the file as it stands now: "
                f"{exc}. If the file moved since the witness was taken, the "
                f"right answer is to escalate rather than overwrite it"
            )
    result.reasons = list(verdict.reasons)
    return result
