"""The six deterministic checks `apply_patch` must pass, as pure functions.

`ARCHITECTURE.md` §6.2.1 is explicit about why this file can exist at all:

    The project's claim is that a deterministic layer, not the model,
    decides whether a write happens. That claim survives because the
    DECISION stays deterministic even though the PAYLOAD is generated:
    every rule below is a plain comparison, evaluated before anything is
    applied, and every one of them can reject.

So the checks are separated from the action, take no client, touch no
filesystem, call nothing, and are individually testable. A reviewer should
be able to read this file and see the whole safety argument for the one
action where a model supplies content.

| # | Constraint | Here |
|---|---|---|
| 1 | Risk tier HIGH, fixed by the action | `RISK_TIER`, and `tier_is_fixed=True` at registration |
| 2 | Only paths the manifest declares in `versioned_paths` | `check_paths` |
| 3 | Git is the inverse; diff against a known blob SHA | `check_against_witness` |
| 4 | Sandbox mandatory, not routed | `permit()`; asserted by `check_sandbox_result` |
| 5 | Diff budget | `check_budget` |
| 6 | Deny-list, absolute, checked on path AND content | `check_denied` |

WHY A UNIFIED DIFF AND NOT THE WHOLE FILE
§6.2.1: *"A patch is proposed as a unified diff against a known blob SHA,
never as a whole file. If the file moved since the witness was taken, the
patch no longer applies and the incident escalates rather than overwriting
someone's work."* That property is free with a diff and impossible with a
whole-file write, which is the entire reason for the inconvenience.

WHAT IS NOT HERE
No command strings, no shell, nothing that executes. A generated *diff* is
data the executor applies; a generated *command* would be arbitrary
execution and `FR-27` forbids it. Nothing in this module runs anything.

WHAT THESE CHECKS DO NOT CATCH, which a reviewer will ask about
They bound WHERE a patch may write, HOW MUCH it may change, and WHETHER it
has an inverse. They do not and cannot judge whether the English in a
prompt is good. A patch that writes a permitted path, stays inside the
budget, adds no denied token and still contains a subtly worse instruction
passes all six.

The backstop for that is constraint 4, and it is the reason the sandbox is
mandatory rather than routed: a prompt that degrades answers fails fast
verification in the clone and never reaches production, whatever the static
checks thought of it. The residual risk is a prompt that answers the three
fast-set questions correctly and is worse in some way those three do not
measure - which is the same residual risk the fast set carries for every
other repair in the catalogue, not a new one introduced here.

Stated plainly because the honest limit of a safety argument is part of it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

RISK_TIER = "HIGH"

# Constraint 5. Small because the only declared versioned path is `prompts`,
# whose files are a few hundred bytes. A patch larger than this is not a
# prompt fix, and §6.2.1's wording is "a large diff is not a repair".
MAX_CHANGED_LINES = 40
MAX_FILES = 2

# Constraint 6, the content half. These are the manifest's `denied_mutations`
# plus the strings that would reach them. Matched case-insensitively against
# ADDED lines only: a diff that DELETES a line mentioning the corpus is not
# the same as one that adds one.
DENIED_CONTENT = (
    "embed_model",
    "embedding_model",
    "nomic-embed-text",
    "drop table",
    "drop database",
    "truncate",
    "delete from",
    "alter table",
    "create extension",
    "document_chunks",
    "pg_dump",
    "psql",
)

# Constraint 6, the path half. Nothing outside the declared versioned paths,
# and never these even if a manifest ever declared them.
DENIED_PATH_PARTS = (
    ".git", ".env", "docker-compose", "Dockerfile", "requirements",
    "pyproject", "alembic", "migrations", "backend/", "evaluation/",
)

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")
_FILE_HEADER = re.compile(r"^\+\+\+ [ab]/(.+)$")


@dataclass
class PatchVerdict:
    """Why a patch may or may not be applied. Reasons, never a bare bool."""

    allowed: bool = False
    reasons: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    added_lines: int = 0
    removed_lines: int = 0

    def deny(self, reason: str) -> PatchVerdict:
        self.allowed = False
        self.reasons.append(reason)
        return self


def parse_files(diff: str) -> list[str]:
    """The paths a unified diff claims to touch, from its `+++` headers."""
    out: list[str] = []
    for line in diff.splitlines():
        m = _FILE_HEADER.match(line)
        if m:
            path = m.group(1).strip()
            if path != "/dev/null":
                out.append(path)
    return out


def added_lines(diff: str) -> list[str]:
    """Lines the patch ADDS, without the marker.

    Added only. A diff that removes a line mentioning `document_chunks` is
    deleting a reference to it, which is not the thing the deny-list is
    about, and treating the two the same would reject safe patches while
    teaching nobody anything.
    """
    return [ln[1:] for ln in diff.splitlines()
            if ln.startswith("+") and not ln.startswith("+++")]


def removed_lines(diff: str) -> list[str]:
    return [ln[1:] for ln in diff.splitlines()
            if ln.startswith("-") and not ln.startswith("---")]


def check_shape(diff: str, v: PatchVerdict) -> PatchVerdict:
    """It must actually be a unified diff, with at least one hunk."""
    if not diff.strip():
        return v.deny("the patch is empty")
    if not any(_HUNK.match(ln) for ln in diff.splitlines()):
        return v.deny(
            "the patch contains no @@ hunk header, so it is not a unified "
            "diff. §6.2.1 requires a diff against a known blob, never a "
            "whole file: a whole-file write silently overwrites work done "
            "since the witness was taken"
        )
    return v


def check_paths(files: list[str], versioned_paths: dict[str, str],
                v: PatchVerdict) -> PatchVerdict:
    """Constraint 2: only paths the manifest declares as versioned."""
    if not files:
        return v.deny("the patch names no file")
    declared = [p.strip("./").rstrip("/") for p in versioned_paths.values()
                if p and not p.startswith("runtime")]
    if not declared:
        return v.deny(
            "the manifest declares no versioned_paths, so there is no file "
            "this action is permitted to write"
        )
    for f in files:
        posix = PurePosixPath(f.replace("\\", "/"))
        if posix.is_absolute() or ".." in posix.parts:
            v.deny(f"path {f!r} escapes the repository")
            continue
        if not any(str(posix).startswith(d) for d in declared):
            v.deny(
                f"path {f!r} is not under any declared versioned path "
                f"({declared}); §6.2.1 permits prompts and config files, "
                f"not the source tree, tests or infrastructure"
            )
    return v


def check_denied(files: list[str], diff: str, denied_mutations: list[str],
                 v: PatchVerdict) -> PatchVerdict:
    """Constraint 6: the deny-list, on path AND on content.

    Checked twice because the two catch different things. A patch to
    `prompts/answer.txt` passes the path check and could still contain
    `DROP TABLE document_chunks`; a patch to `backend/db.py` fails the path
    check whatever it contains.
    """
    for f in files:
        low = f.lower()
        for part in DENIED_PATH_PARTS:
            if part.lower() in low:
                v.deny(f"path {f!r} matches the denied path fragment {part!r}")

    for line in added_lines(diff):
        low = line.lower()
        for token in DENIED_CONTENT:
            if token in low:
                v.deny(
                    f"the patch ADDS a line containing {token!r}, which the "
                    f"deny-list refuses on content regardless of path: "
                    f"{line.strip()[:80]!r}"
                )
    # The manifest's own list, so a project that denies more is honoured.
    for mutation in denied_mutations:
        token = mutation.replace("_change", "").replace("_", " ")
        for line in added_lines(diff):
            if token and token in line.lower():
                v.deny(
                    f"the patch ADDS a line matching the manifest's denied "
                    f"mutation {mutation!r}"
                )
    return v


def check_budget(diff: str, files: list[str], v: PatchVerdict) -> PatchVerdict:
    """Constraint 5: a large diff is not a repair."""
    added = added_lines(diff)
    removed = removed_lines(diff)
    v.added_lines = len(added)
    v.removed_lines = len(removed)
    changed = len(added) + len(removed)
    if changed > MAX_CHANGED_LINES:
        v.deny(
            f"the patch changes {changed} lines, over the budget of "
            f"{MAX_CHANGED_LINES}. §6.2.1: a large diff is not a repair"
        )
    if len(set(files)) > MAX_FILES:
        v.deny(
            f"the patch touches {len(set(files))} files, over the budget of "
            f"{MAX_FILES}"
        )
    return v


def check_against_witness(
    files: list[str], witness: dict[str, str], v: PatchVerdict,
) -> PatchVerdict:
    """Constraint 3's precondition: every file has a recorded pre-state.

    The witness maps path -> the blob digest captured before the incident.
    A file with no witness cannot be reverted to anything, so a patch to it
    has no inverse, and `executor/base.py` makes an action without an
    inverse unrepresentable.
    """
    for f in files:
        if f not in witness:
            v.deny(
                f"no pre-state witness was captured for {f!r}, so this patch "
                f"would have no inverse. An action without a working inverse "
                f"cannot be applied (ARCHITECTURE.md §6.0)"
            )
    return v


def check_sandbox_result(sandbox_passed: bool | None,
                         v: PatchVerdict) -> PatchVerdict:
    """Constraint 4: no sandbox result, no proposal.

    `None` is the dangerous value and is treated as a refusal: it means the
    sandbox never ran, which is indistinguishable from "we did not check".
    """
    if sandbox_passed is None:
        return v.deny(
            "the patch has no sandbox result. §6.2.1 makes the sandbox "
            "mandatory rather than routed: no sandbox result, no proposal"
        )
    if not sandbox_passed:
        return v.deny(
            "the patch did not pass fast verification in the sandbox, so it "
            "does not reach production. This is the sandbox doing its job"
        )
    return v


def evaluate_static(
    diff: str,
    versioned_paths: dict[str, str],
    denied_mutations: list[str],
    witness: dict[str, str],
) -> PatchVerdict:
    """The five checks answerable from the patch alone.

    SPLIT FROM `evaluate` BECAUSE THE SIXTH IS A DIFFERENT KIND OF QUESTION,
    and a test made that obvious. Five of the constraints ask "is this patch
    permitted" and can be answered the moment the model replies. Constraint
    4 asks "what happened when it was tried", which has no answer until a
    sandbox has run.

    Calling the full `evaluate` at proposal time therefore always denied -
    correctly, since `None` means nobody checked - and that denial short-
    circuited the applicability test, so a proposal could never be found
    worth sandboxing in the first place. The sandbox was gating the road to
    the sandbox.

    So: this at proposal time, `evaluate` before anything is written.
    """
    v = PatchVerdict()
    check_shape(diff, v)
    files = parse_files(diff)
    v.files = files
    check_paths(files, versioned_paths, v)
    check_denied(files, diff, denied_mutations, v)
    check_budget(diff, files, v)
    check_against_witness(files, witness, v)
    v.allowed = not v.reasons
    return v


def evaluate(
    diff: str,
    versioned_paths: dict[str, str],
    denied_mutations: list[str],
    witness: dict[str, str],
    sandbox_passed: bool | None = None,
) -> PatchVerdict:
    """All six checks. THE gate before anything is written to production.

    Every rule runs even after one fails: an operator reading a refusal
    should see everything wrong with a patch, not play whack-a-mole with it
    one rule at a time.
    """
    v = evaluate_static(diff, versioned_paths, denied_mutations, witness)
    check_sandbox_result(sandbox_passed, v)
    v.allowed = not v.reasons
    return v
