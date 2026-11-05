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
