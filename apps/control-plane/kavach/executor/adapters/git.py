"""Applying a unified diff. The only thing in Kavach that runs `git`.

`ARCHITECTURE.md` §6.2.1: *"The model never executes `git`. It emits diff
text; `executor/adapters/git.py` is the only thing that touches a
repository."* This is that file.

THERE IS NO COMMIT PATH AND NO PUSH PATH, AND THAT IS THE POINT
`AGENTS.md` rule 10 requires that Kavach never pushes, never amends, never
force-pushes and never touches `main` or the user's working branch.
`ARCHITECTURE.md` §13 states the enforcement as *"No `git push` code path
exists"*.

The strongest way to honour that is not to write the code and then refuse
it. This module exposes `check` and `apply` and nothing else. There is no
function here that commits, branches, pushes, resets or checks out, so
there is nothing for a bug, a typo or a future edit to reach. A guard can
be bypassed; an absent code path cannot.

IT DOES NOT EVEN NEED A REPOSITORY
`git apply` works outside a work tree, as a standalone patch tool operating
on files relative to a directory. The sandbox's prompts are a working copy
regenerated from production on every seed, deliberately gitignored so a
model's experimental patch can never be swept into a commit by `git add
-A`. So this adapter runs with no repository in play at all, which removes
the whole class of risk rule 10 is about rather than guarding against it.

`--recount` IS PASSED, AND IT IS NOT A WEAKENING
A language model reliably gets the CONTENT of context lines right and the
NUMBERS in `@@ -1,4 +1,5 @@` wrong - it is counting, which is the thing
these models are worst at. `--recount` tells git to derive those counts
from the hunk body instead of trusting the header.

It does not relax matching. The context lines themselves must still be
found, in order, in the file, so the property this whole design rests on -
a patch against a moved file is rejected - is untouched. What it removes is
a failure mode that has nothing to do with whether the repair is correct.
The alternative was asking the model to count, and `rca/schema.py` already
records what asking a small model nicely is worth.

WHY `git apply` AND NOT A HAND-WRITTEN PATCHER
`--check` gives the property §6.2.1 asks for, for free: *"If the file moved
since the witness was taken, the patch no longer applies and the incident
escalates rather than overwriting someone's work."* A diff whose context
lines no longer match is REJECTED rather than forced. Reimplementing
three-way context matching to avoid a dependency that is already installed
would be more code and worse code.

EVERY WRITE IS FENCED TO ONE DIRECTORY
`--directory` roots the patch, and the resolved root must be inside the
caller-supplied boundary. `--unsafe-paths` is never passed, so paths that
escape via `..` are refused by git itself as well as by
`patch_checks.check_paths` before the diff ever reaches here. Two
independent refusals for the same mistake, which is the intent.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

# Everything this module may run. There is no entry here that writes
# history, and adding one would be the thing rule 10 forbids.
_GIT_APPLY = "apply"


class GitAdapterError(RuntimeError):
    """A patch could not be applied, or was refused before being applied."""


def _as_patch_file(diff: str) -> str:
    """Terminate the final line. Nothing else.

    `git apply` reads a patch whose last line has no newline as truncated
    and reports `corrupt patch at line N`, which says nothing about the
    cause. A model returns its diff as a JSON string, and a JSON string
    ends where the content ends, so the final hunk line arrives
    unterminated almost every time.

    This was the single largest cause of rejected patches: gpt-oss-120b
    produced diffs whose headers, markers and context lines were all
    correct and which applied cleanly the moment a newline was appended.
    The rate it was costing was being read as a model capability limit.

    It is the same category of accommodation as `--recount`: a formatting
    artifact of how the text was transported is forgiven, and nothing about
    the CONTENT is. Appending a newline cannot change which lines match,
    which are added, or which are removed - a patch that was going to be
    rejected for touching the wrong file, or for context that no longer
    exists, is rejected identically afterwards.
    """
    return diff if diff.endswith("\n") else diff + "\n"


def _run(args: list[str], cwd: Path, timeout_s: float = 60.0) -> str:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            timeout=timeout_s, check=False,
            # UTF-8 explicitly: the Windows default is cp1252 and a prompt
            # file may hold anything. Seeding the sandbox already died on
            # this once.
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError as exc:
        raise GitAdapterError("git is not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitAdapterError(f"git {args[0]} timed out") from exc
    if proc.returncode != 0:
        raise GitAdapterError(
            f"git {args[0]} failed ({proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()[:400]}"
        )
    return proc.stdout


def _fence(root: Path, boundary: Path) -> Path:
    """Refuse any root that is not inside the boundary the caller allows."""
    r = root.resolve()
    b = boundary.resolve()
    if r != b and b not in r.parents:
        raise GitAdapterError(
            f"refusing to apply a patch rooted at {r}: it is outside the "
            f"permitted boundary {b}"
        )
    if not r.is_dir():
        raise GitAdapterError(f"no such directory to patch: {r}")
    return r


def check(diff: str, root: Path, boundary: Path, strip: int = 1) -> None:
    """Would this patch apply cleanly? Raises if not. Writes nothing.

    This is the half that matters most. A diff whose context no longer
    matches the file means the file changed since the witness was taken,
    and §6.2.1 is explicit that the right response is to escalate rather
    than overwrite whatever is there now.
    """
    r = _fence(root, boundary)
    if not diff.strip():
        raise GitAdapterError("refusing to apply an empty patch")
    with tempfile.TemporaryDirectory() as tmp:
        patch_file = Path(tmp) / "incident.diff"
        patch_file.write_text(_as_patch_file(diff), encoding="utf-8",
                              newline="")
        _run([_GIT_APPLY, "--check", "--recount", f"-p{strip}",
              str(patch_file)], cwd=r)


def apply(diff: str, root: Path, boundary: Path, strip: int = 1) -> list[str]:
    """Apply the patch, having checked it first. Returns the paths written.

    `--check` runs again here rather than trusting an earlier call: between
    a proposal being made and a human approving it, the file may have moved.
    Re-checking costs milliseconds and is the difference between a stale
    approval and an overwrite.
    """
    r = _fence(root, boundary)
    check(diff, r, boundary, strip)
    with tempfile.TemporaryDirectory() as tmp:
        patch_file = Path(tmp) / "incident.diff"
        patch_file.write_text(_as_patch_file(diff), encoding="utf-8",
                              newline="")
        # --numstat first, so the return value reports what git itself says
        # was touched rather than what the diff's headers claimed.
        stat = _run([_GIT_APPLY, "--numstat", "--recount", f"-p{strip}",
                     str(patch_file)], cwd=r)
        _run([_GIT_APPLY, "--recount", f"-p{strip}", str(patch_file)], cwd=r)
    written = []
    for line in stat.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            written.append(parts[2])
    return written
