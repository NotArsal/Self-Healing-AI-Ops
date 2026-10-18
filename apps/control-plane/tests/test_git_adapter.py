"""The git adapter: what it applies, what it refuses, and what it cannot do.

Two properties carry most of the weight.

**It fails when the file moved.** `ARCHITECTURE.md` §6.2.1 chose a unified
diff over a whole file precisely so that a patch written against a stale
witness is REJECTED rather than forced. That is a property of `git apply`,
not of our code, so it is tested rather than assumed.

**It has no history-writing code path at all.** `AGENTS.md` rule 10 and
§13's "no `git push` code path exists" are honoured by absence rather than
by a guard, so the test asserts the absence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kavach.executor.adapters import git


def write(root: Path, name: str, text: str) -> Path:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="")
    return p


def diff_for(name: str, old: str, new: str) -> str:
    return (f"--- a/{name}\n+++ b/{name}\n@@ -1,1 +1,1 @@\n-{old}\n+{new}\n")


@pytest.fixture
def area(tmp_path: Path) -> Path:
    write(tmp_path, "answer.txt", "old line\n")
    return tmp_path


# --- the happy path, once --------------------------------------------------


def test_a_clean_patch_applies_and_reports_what_it_wrote(area: Path) -> None:
    written = git.apply(diff_for("answer.txt", "old line", "new line"),
                        area, area)
    assert (area / "answer.txt").read_text(encoding="utf-8") == "new line\n"
    assert written == ["answer.txt"]


# --- THE property the whole design rests on --------------------------------


def test_a_patch_against_a_moved_file_is_refused_not_forced(
    area: Path,
) -> None:
    """§6.2.1: "If the file moved since the witness was taken, the patch no
    longer applies and the incident escalates rather than overwriting
    someone's work." This is why a diff, and not a whole file."""
    patch = diff_for("answer.txt", "old line", "new line")
    # Someone edits the file after the patch was written.
    write(area, "answer.txt", "a human changed this\n")

    with pytest.raises(git.GitAdapterError):
        git.check(patch, area, area)
    assert (area / "answer.txt").read_text(encoding="utf-8") == (
        "a human changed this\n"
    ), "the human's edit was overwritten"


def test_apply_rechecks_rather_than_trusting_an_earlier_check(
    area: Path,
) -> None:
    """Between a proposal and a human approving it, the file can move. A
    stale approval must not become an overwrite."""
    patch = diff_for("answer.txt", "old line", "new line")
    git.check(patch, area, area)          # passes now
    write(area, "answer.txt", "moved on\n")   # and then the world changes

    with pytest.raises(git.GitAdapterError):
        git.apply(patch, area, area)
    assert (area / "answer.txt").read_text(encoding="utf-8") == "moved on\n"


# --- the fence -------------------------------------------------------------


def test_a_root_outside_the_boundary_is_refused(tmp_path: Path) -> None:
    inside = tmp_path / "sandbox"
    outside = tmp_path / "production"
    inside.mkdir()
    outside.mkdir()
    write(outside, "answer.txt", "old line\n")

    with pytest.raises(git.GitAdapterError, match="outside the permitted"):
        git.apply(diff_for("answer.txt", "old line", "new line"),
                  outside, inside)
    assert (outside / "answer.txt").read_text(encoding="utf-8") == "old line\n"


def test_a_missing_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(git.GitAdapterError, match="no such directory"):
        git.check("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
                  tmp_path / "nope", tmp_path)


def test_an_empty_patch_is_refused(area: Path) -> None:
    with pytest.raises(git.GitAdapterError, match="empty patch"):
        git.check("   \n", area, area)


def test_a_patch_escaping_via_dotdot_does_not_write_outside(
    tmp_path: Path,
) -> None:
    """`patch_checks.check_paths` refuses these before they reach here, and
    git refuses them again. Two independent refusals for one mistake."""
    area = tmp_path / "sandbox"
    area.mkdir()
    secret = write(tmp_path, "secret.txt", "untouched\n")
    escaping = ("--- a/../secret.txt\n+++ b/../secret.txt\n"
                "@@ -1,1 +1,1 @@\n-untouched\n+owned\n")

    with pytest.raises(git.GitAdapterError):
        git.apply(escaping, area, area)
    assert secret.read_text(encoding="utf-8") == "untouched\n"


# --- honoured by absence, not by a guard -----------------------------------


def test_the_adapter_has_no_history_writing_code_path() -> None:
    """AGENTS.md rule 10 and §13's "no `git push` code path exists". A guard
    can be bypassed; an absent function cannot. So this asserts the module
    simply does not contain one."""
    source = Path(git.__file__).read_text(encoding="utf-8")
    for forbidden in ("push", "commit", "reset", "checkout", "rebase",
                      "--force", "--amend", "branch"):
        assert f'"{forbidden}"' not in source, (
            f"the git adapter contains a {forbidden!r} argument; rule 10 is "
            f"honoured by having no such code path, not by guarding one"
        )
    assert sorted(n for n in dir(git) if not n.startswith("_")
                  and callable(getattr(git, n))) == [
        "GitAdapterError", "Path", "apply", "check",
    ]


# --- --recount: forgiving about counting, strict about content -------------


def test_wrong_hunk_line_numbers_still_apply_if_the_context_matches(
    area: Path,
) -> None:
    """A language model gets context lines right and the numbers in
    `@@ -1,4 +1,5 @@` wrong, because that is counting. `--recount` derives
    the counts from the hunk body, which removes a failure mode that has
    nothing to do with whether the repair is correct."""
    write(area, "answer.txt", "alpha\nbeta\ngamma\n")
    nonsense_numbers = (
        "--- a/answer.txt\n+++ b/answer.txt\n"
        "@@ -99,7 +42,3 @@\n alpha\n-beta\n+BETA\n gamma\n"
    )
    git.apply(nonsense_numbers, area, area)
    assert (area / "answer.txt").read_text(encoding="utf-8") == (
        "alpha\nBETA\ngamma\n"
    )


def test_recount_does_not_make_wrong_context_acceptable(area: Path) -> None:
    """THE check that --recount is not a weakening. The numbers may be
    wrong; the context lines may not."""
    write(area, "answer.txt", "alpha\nbeta\ngamma\n")
    wrong_context = (
        "--- a/answer.txt\n+++ b/answer.txt\n"
        "@@ -1,3 +1,3 @@\n alpha\n-NOT THE REAL LINE\n+BETA\n gamma\n"
    )
    with pytest.raises(git.GitAdapterError):
        git.apply(wrong_context, area, area)
    assert (area / "answer.txt").read_text(encoding="utf-8") == (
        "alpha\nbeta\ngamma\n"
    )
