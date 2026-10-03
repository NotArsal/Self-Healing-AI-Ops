"""Fast verification — the three deterministic probes (FR-07).

Shared by baseline capture and by the healing loop deliberately: a verification
result is only comparable to a baseline if both were produced by the same code.
Two implementations of "did the fast set pass" would drift, and the drift would
show up as a false heal.

All checks are string operations (FR-07b). No LLM judge, no embedding
similarity, no RAGAS, no cloud API, and therefore nothing nondeterministic in
the recovery path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from kavach.target import TargetClient, TargetError

# Mirrors the target's own refusal strings in rag.py.
REFUSAL_MARKERS = ("don't know", "do not know", "no mention", "don't have any documents")
SOURCES_MARKER = "**sources:**"


@dataclass
class CaseResult:
    case_id: str
    question: str
    expected_keyword: str
    keyword_present: bool
    non_refusal: bool
    sources_block: bool
    latency_s: float
    error: str = ""

    @property
    def passed(self) -> bool:
        """All three must hold.

        sources_block is not optional: an answer the model produced from its own
        parameters would satisfy the other two while proving nothing about
        retrieval, and would report healthy with retrieval destroyed.
        """
        return self.keyword_present and self.non_refusal and self.sources_block


@dataclass
class FastVerificationResult:
    cases: list[CaseResult] = field(default_factory=list)
    total_s: float = 0.0
    budget_s: int = 120
    health_ok: bool = False
    health_detail: str = ""

    @property
    def quality_ok(self) -> bool:
        return bool(self.cases) and all(c.passed for c in self.cases)

    @property
    def within_budget(self) -> bool:
        return self.total_s <= self.budget_s

    @property
    def passed(self) -> bool:
        """Probe 1 health, probe 2 latency budget, probe 3 quality."""
        return self.health_ok and self.quality_ok and self.within_budget

    @property
    def pass_rate(self) -> float:
        return (sum(c.passed for c in self.cases) / len(self.cases)) if self.cases else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "health_ok": self.health_ok,
            "health_detail": self.health_detail,
            "quality_ok": self.quality_ok,
            "within_budget": self.within_budget,
            "pass_rate": self.pass_rate,
            "total_s": round(self.total_s, 2),
            "budget_s": self.budget_s,
            "cases": [
                {
                    "case_id": c.case_id,
                    "passed": c.passed,
                    "keyword_present": c.keyword_present,
                    "non_refusal": c.non_refusal,
                    "sources_block": c.sources_block,
                    "latency_s": round(c.latency_s, 2),
                    "error": c.error,
                }
                for c in self.cases
            ],
        }

    def render(self) -> str:
        lines = [
            f"Fast verification: {'PASS' if self.passed else 'FAIL'}",
            f"  health      {'ok' if self.health_ok else 'FAIL'}  {self.health_detail}",
            f"  budget      {self.total_s:.1f}s / {self.budget_s}s"
            f"  {'ok' if self.within_budget else 'EXCEEDED'}",
            f"  quality     {self.pass_rate:.0%}",
        ]
        for c in self.cases:
            bits = (f"kw={c.keyword_present} nonref={c.non_refusal} "
                    f"grounded={c.sources_block}")
            lines.append(f"    [{'PASS' if c.passed else 'FAIL'}] {c.case_id} "
                         f"{c.latency_s:5.1f}s  {bits}" + (f"  {c.error}" if c.error else ""))
        return "\n".join(lines)


def load_cases(path: str | Path) -> tuple[list[dict[str, Any]], int]:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    cases = doc.get("cases", [])
    budget = int((doc.get("budget") or {}).get("max_duration_s", 120))
    return cases, budget


def resolve_set(declared: str, kavach_root: str | Path) -> Path | None:
    root = Path(kavach_root)
    for candidate in (root / declared, root / "apps/control-plane" / declared):
        if candidate.is_file():
            return candidate
    return None


def run(
    client: TargetClient,
    fast_set_path: str | Path,
    check_health: bool = True,
) -> FastVerificationResult:
    """Run the set serially, never concurrently."""
    cases, budget = load_cases(fast_set_path)
    result = FastVerificationResult(budget_s=budget)

    if check_health:
        try:
            h = client.health()
            result.health_ok = h.get("status") == "ok"
            deps = h.get("dependencies", {})
            result.health_detail = ", ".join(
                f"{k}={'ok' if v.get('ok') else 'FAIL'}" for k, v in deps.items()
            )
        except TargetError as exc:
            result.health_ok = False
            result.health_detail = str(exc)
    else:
        result.health_ok = True
        result.health_detail = "skipped"

    started = time.perf_counter()
    for case in cases:
        cid = str(case.get("id", "?"))
        q = str(case["question"])
        kw = str(case["expected_keyword"])
        t0 = time.perf_counter()
        try:
            answer = client.ask(q)
        except TargetError as exc:
            result.cases.append(CaseResult(cid, q, kw, False, False, False,
                                           time.perf_counter() - t0, str(exc)))
            continue
        low = answer.lower()
        result.cases.append(CaseResult(
            case_id=cid, question=q, expected_keyword=kw,
            keyword_present=kw.lower() in low,
            non_refusal=not any(m in low for m in REFUSAL_MARKERS),
            sources_block=SOURCES_MARKER in low,
            latency_s=time.perf_counter() - t0,
        ))
    result.total_s = time.perf_counter() - started
    return result
