"""Guards for `harness/fastset_parallel.py`.

The script's claim is that serial and parallel are judged by the SAME rules,
so these check that the split copies keep the set's markers and budget, that a
parallel run still fails on health alone (the F02 detection question), and
that it refuses to start while a bench or a fault may be live.

No network, no Docker, no model. `AGENTS.md` PL-02.
"""

from __future__ import annotations

import io
import json
import urllib.request
from pathlib import Path
from typing import Any

import pytest
import yaml

from harness import fastset_parallel as fp
from kavach.verification import fast


class _FakeTarget:
    """Answers every fast-set question correctly, with sources."""

    def __init__(self, healthy: bool = True) -> None:
        cases = yaml.safe_load(fp.FAST_SET.read_text("utf-8"))["cases"]
        self.answers = {c["question"]: f"It is {c['expected_keyword']}. **Sources:** x"
                        for c in cases}
        self.healthy = healthy

    def health(self, timeout: float = 10.0) -> dict[str, Any]:
        return {"status": "ok" if self.healthy else "degraded", "dependencies": {}}

    def ask(self, question: str, timeout: float = 240.0) -> str:
        return self.answers[question]


def test_split_keeps_everything_but_the_cases(tmp_path: Path) -> None:
    real = yaml.safe_load(fp.FAST_SET.read_text("utf-8"))
    health_only, singles = fp.split_set(fp.FAST_SET, tmp_path)
    assert yaml.safe_load(health_only.read_text("utf-8"))["cases"] == []
    assert len(singles) == len(real["cases"]) == 3
    for p, case in zip(singles, real["cases"], strict=True):
        doc = yaml.safe_load(p.read_text("utf-8"))
        assert doc["cases"] == [case]
        assert doc["refusal_markers"] == real["refusal_markers"]
        assert doc["sources_marker"] == real["sources_marker"]
        assert doc["budget"] == real["budget"]


def test_parallel_passes_like_serial_on_a_healthy_target(tmp_path: Path) -> None:
    client: Any = _FakeTarget()
    health_only, singles = fp.split_set(fp.FAST_SET, tmp_path)
    par = fp.run_parallel(client, health_only, singles)
    ser = fast.run(client, fp.FAST_SET)
    assert par.passed and ser.passed
    assert [c.case_id for c in par.cases] == [c.case_id for c in ser.cases]
    assert par.budget_s == ser.budget_s == 120


def test_parallel_still_fails_when_only_health_fails(tmp_path: Path) -> None:
    # Under F02 a parallel set may finish inside 120s; it must still fail if
    # /healthz does, or parallel probing would hide the fault from detection.
    client: Any = _FakeTarget(healthy=False)
    health_only, singles = fp.split_set(fp.FAST_SET, tmp_path)
    r = fp.run_parallel(client, health_only, singles)
    assert r.within_budget and r.quality_ok
    assert not r.passed


def test_summary_counts_and_speedup() -> None:
    rows = [
        {"mode": "serial", "passed": True, "health_ok": True,
         "within_budget": True, "quality_ok": True, "total_s": 18.0},
        {"mode": "parallel", "passed": False, "health_ok": True,
         "within_budget": True, "quality_ok": False, "total_s": 6.0},
    ]
    s = fp.summarise(rows)
    assert s["serial"]["passed"] == 1 and s["parallel"]["passed"] == 0
    assert s["parallel"]["quality_ok"] == 0
    assert s["speedup_median"] == 3.0


def _system(loop_running: bool) -> Any:
    def urlopen(url: str, timeout: float = 0) -> io.BytesIO:
        return io.BytesIO(json.dumps({"loop_running": loop_running}).encode())
    return urlopen


@pytest.mark.parametrize(("loop_running", "toxics", "refused"), [
    (True, [], True),
    (False, [{"name": "f02_latency"}], True),
    (False, [], False),
])
def test_refuses_while_a_run_or_a_fault_may_be_live(
    monkeypatch: pytest.MonkeyPatch, loop_running: bool,
    toxics: list[dict[str, str]], refused: bool,
) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _system(loop_running))
    monkeypatch.setattr(fp, "_call", lambda path: toxics)
    assert bool(fp.refuse_reason()) is refused
