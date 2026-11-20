"""`make bench` on another corpus is opt-in, refused on drift, and kept apart.

The bench refuses any corpus but the paper's (30 chunks / 2 files), because
every number it prints would otherwise describe a corpus nobody can name.
A separate experiment states its corpus explicitly instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.report import EXPECTED_CORPUS, expected_corpus  # noqa: E402


def test_without_the_flag_it_is_the_papers_corpus() -> None:
    assert expected_corpus("") == (EXPECTED_CORPUS, False)


def test_the_flag_states_the_experiment_corpus() -> None:
    assert expected_corpus("1909,4") == ({"chunks": 1909.0, "files": 4.0}, True)


@pytest.mark.parametrize("bad", ["1909", "a,b", "1,2,3"])
def test_a_malformed_flag_stops_the_bench(bad: str) -> None:
    with pytest.raises(SystemExit, match="CHUNKS,FILES"):
        expected_corpus(bad)
