"""A document that cites a test by name must cite one that exists.

ADDED 2026-11-05, in the same breath as the citations it checks.

`ROADMAP.md`'s P7 acceptance list was rewritten to mark six patch-safety
criteria met, each naming the test that holds it so a reader can check the
claim instead of trusting it. That is better than a bare tick and it creates a
new way to be wrong: rename or delete a test and the roadmap goes on asserting
the criterion is met, citing something that is no longer there.

That is this project's recurring defect in miniature - a fact recorded in one
place and nothing checking the other place still agrees - which is the reason
to spend twenty lines on it rather than trust a convention. The four defects
found this week were all this shape: a health flag the write path enforced and
the read path ignored, a refusal vocabulary declared in YAML and read by
nothing, an audit metric that counted the wrong denominator, and service
addresses correct on the host and wrong in the container.

It deliberately checks only that the name EXISTS. Whether the test still
proves what the roadmap says it proves is a question no regex can answer, and
pretending otherwise would be a worse guarantee than none.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TESTS = ROOT / "apps" / "control-plane" / "tests"
DOCS = sorted((ROOT / "docs").glob("*.md"))


def defined_test_names() -> set[str]:
    names: set[str] = set()
    for path in TESTS.glob("test_*.py"):
        names |= set(re.findall(r"^def (test_[a-z0-9_]+)\(",
                                path.read_text(encoding="utf-8"), re.M))
    return names


def cited() -> list[tuple[str, str]]:
    """(document, test name) for every `::test_...` citation in docs/."""
    out: list[tuple[str, str]] = []
    for doc in DOCS:
        for name in re.findall(r"::(test_[a-z0-9_]+)",
                               doc.read_text(encoding="utf-8")):
            out.append((doc.name, name))
    return out


def test_there_are_tests_and_citations_to_check() -> None:
    """A guard on the guard: either side coming back empty would make the
    check below pass by having nothing to disagree about."""
    assert defined_test_names(), f"no test functions found under {TESTS}"
    assert cited(), (
        "no document cites a test by name; if the citations were "
        "deliberately removed, delete this file too rather than leaving a "
        "test that can only pass")


@pytest.mark.parametrize("doc,name", cited(), ids=lambda v: str(v))
def test_a_cited_test_exists(doc: str, name: str) -> None:
    assert name in defined_test_names(), (
        f"{doc} cites `{name}` as the test that holds one of its claims, and "
        f"no test of that name exists. Either the test was renamed - in which "
        f"case update the citation - or it was deleted, in which case the "
        f"claim in {doc} is no longer backed by anything and should not keep "
        f"its tick.")


# --- decision records -------------------------------------------------------
#
# Same invariant, other citation style. The report leans on ADR numbers to
# carry arguments it does not restate - "ADR 0013 identifies the real one",
# "the reasoning is in ADR 0012" - so a number pointing at nothing is an
# argument with its support removed. Fourteen are cited across docs/ and all
# fourteen resolve today.
#
# Uncited records are fine and are not checked: a decision worth recording is
# worth recording whether or not the report happens to reference it.

ADR_DIR = ROOT / "docs" / "decisions"


def adrs_on_disk() -> set[int]:
    numbers: set[int] = set()
    for path in ADR_DIR.glob("*.md"):
        found = re.match(r"(\d{4})-", path.name)
        if found:
            numbers.add(int(found.group(1)))
    return numbers


def adrs_cited() -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for doc in DOCS:
        for number in re.findall(r"ADR\s*0*(\d{1,4})",
                                 doc.read_text(encoding="utf-8")):
            out.setdefault(int(number), set()).add(doc.name)
    return out


def test_there_are_decision_records_to_check() -> None:
    assert ADR_DIR.is_dir(), f"no decisions directory at {ADR_DIR}"
    assert adrs_on_disk(), "no ADR files found; the naming may have changed"
    assert adrs_cited(), "no document cites an ADR, which would be a surprise"


def test_every_cited_decision_record_exists() -> None:
    on_disk = adrs_on_disk()
    missing = {n: sorted(where) for n, where in adrs_cited().items()
               if n not in on_disk}
    assert not missing, (
        "these ADR numbers are cited and no file answers to them, so the "
        "arguments resting on them point at nothing: "
        + ", ".join(f"ADR {n:04d} (in {', '.join(w)})"
                    for n, w in sorted(missing.items())))
