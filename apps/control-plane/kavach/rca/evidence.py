"""Evidence normalisation — the frame the RCA engine reasons over.

Collects real signals from the running system into stable, individually
citable items. The LLM cites items by ID, and validation then checks every
cited ID against this frame, which is what makes a diagnosis auditable rather
than merely plausible (FR-10, UX-04).

IDs are stable and short (`EV-M01`, `EV-C01`, …) so they survive the ~768-token
compression budget the decision model will later impose, and so a human reading
the audit trail can resolve a citation by eye.

TWO THINGS DELIBERATELY EXCLUDED

User content. The target logs `Received chat question: '<question>'`, which is
user data. Those lines are filtered out before anything reaches the model: token
counts are telemetry, question text is not (FR-28). Shipping the corpus or user
questions into a prompt would also make the evidence frame a data-egress path.

Interpretation. Each item carries its observed value and the healthy
expectation, never a verdict. The deterministic detector forms verdicts; if
this module pre-chewed the answer, the LLM would be grading my conclusion
instead of the evidence, and the comparison between the two would be worthless.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from kavach.target import TargetClient, TargetError
from kavach.verification.fast import FastVerificationResult

# Signals the detector and RCA share, so both reason over the same numbers.
METRIC_QUERIES: dict[str, str] = {
    "retrieval_top_similarity_p50": (
        "histogram_quantile(0.50, sum by (le) "
        "(rate(ragapp_retrieval_top_similarity_bucket[10m])))"
    ),
    "retrieval_kept_chunks_mean": (
        "rate(ragapp_retrieval_kept_chunks_sum[10m]) "
        "/ clamp_min(rate(ragapp_retrieval_kept_chunks_count[10m]), 1e-9)"
    ),
    "retrieval_empty_context_ratio": (
        "(sum(rate(ragapp_retrieval_empty_context_total[10m])) or vector(0)) "
        "/ clamp_min(sum(rate(ragapp_retrieval_kept_chunks_count[10m])), 1e-9)"
    ),
    "corpus_chunks": "ragapp_corpus_chunks",
    "corpus_files": "ragapp_corpus_files",
    "llm_error_ratio": (
        '(sum(rate(ragapp_llm_requests_total{outcome="error"}[5m])) or vector(0)) '
        "/ clamp_min(sum(rate(ragapp_llm_requests_total[5m])), 1e-9)"
    ),
    "llm_generation_latency_p95": (
        "histogram_quantile(0.95, sum by (le) "
        '(rate(ragapp_llm_duration_seconds_bucket{operation="generation"}[5m])))'
    ),
    "db_pool_in_use": "max(ragapp_db_pool_in_use)",
    "chat_error_ratio": (
        '(sum(rate(http_requests_total{handler="/v1/chat",status="5xx"}[5m])) or vector(0))'
        ' / clamp_min(sum(rate(http_requests_total{handler="/v1/chat"}[5m])), 1e-9)'
    ),
}

# Healthy expectations, from the captured baseline. Stated so the model can see
# observed-vs-expected without being handed a conclusion.
HEALTHY_EXPECTATION: dict[str, str] = {
    "retrieval_top_similarity_p50": ">= 0.50 (measured healthy 0.658)",
    "retrieval_kept_chunks_mean": ">= 1.0 (measured healthy 2.73)",
    "retrieval_empty_context_ratio": "< 0.20 (measured healthy 0.0)",
    "corpus_chunks": "30 (the onboarded corpus)",
    "corpus_files": "2 (919.pdf, 1662.pdf)",
    "llm_error_ratio": "< 0.20 (measured healthy 0.0)",
    "llm_generation_latency_p95": "< 4.0s (measured healthy 0.94s)",
    "db_pool_in_use": "well under the max of 10 (measured healthy 0)",
    "chat_error_ratio": "< 0.05 (measured healthy 0.0)",
}

# Log lines worth showing. Anything matching USER_CONTENT is dropped first.
LOG_SIGNAL = re.compile(
    r"Reranked|kept \d+ chunks|Cannot connect|timed out|Error|ERROR|Traceback"
    r"|expansion queries|Failed",
)
USER_CONTENT = re.compile(
    r"Received chat question|Generated Queries for expansion|answer=|question=",
)


@dataclass
class EvidenceItem:
    eid: str
    kind: str          # metric | config | verification | health | log | baseline
    name: str
    value: Any
    expected: str = ""
    note: str = ""

    def render(self) -> str:
        line = f"{self.eid} [{self.kind}] {self.name} = {self.value}"
        if self.expected:
            line += f"  (healthy: {self.expected})"
        if self.note:
            line += f"  — {self.note}"
        return line


@dataclass
class EvidenceFrame:
    """Everything RCA is allowed to see, and the only source of valid citations."""

    collected_at: str = ""
    items: list[EvidenceItem] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def add(self, **kw: Any) -> EvidenceItem:
        item = EvidenceItem(**kw)
        self.items.append(item)
        return item

    @property
    def ids(self) -> set[str]:
        return {i.eid for i in self.items}

    def by_id(self, eid: str) -> EvidenceItem | None:
        return next((i for i in self.items if i.eid == eid), None)

    def metric(self, name: str) -> float | None:
        item = next((i for i in self.items
                     if i.kind == "metric" and i.name == name), None)
        if item is None or item.value is None:
            return None
        try:
            return float(item.value)
        except (TypeError, ValueError):
            return None

    def render(self) -> str:
        return "\n".join(i.render() for i in self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "collected_at": self.collected_at,
            "problems": self.problems,
            "items": [
                {"eid": i.eid, "kind": i.kind, "name": i.name, "value": i.value,
                 "expected": i.expected, "note": i.note}
                for i in self.items
            ],
        }


def _recent_logs(container: str, tail: int = 60, keep: int = 10) -> list[str]:
    """Recent target log lines, with user content stripped.

    Read-only: it reads a log stream and never execs into the container.
    """
    try:
        import docker

        client = docker.from_env()
        try:
            c = client.containers.get(container)
            raw = c.logs(tail=tail).decode("utf-8", "replace")
        finally:
            client.close()
    except Exception:
        return []

    out: list[str] = []
    for line in raw.splitlines():
        if USER_CONTENT.search(line):
            continue           # user data never reaches the prompt
        if LOG_SIGNAL.search(line):
            out.append(line.strip()[:220])
    return out[-keep:]


NO_DATA_NOTE = (
    "NO DATA. The series returned nothing, or returned NaN because the "
    "underlying histogram has no observations in the window. This is MISSING, "
    "not zero and not healthy: you may not infer a value for it, and you may "
    "not cite it as evidence of health"
)


def reading(value: float | None) -> tuple[float | None, str]:
    """One metric reading as the model should see it, plus its note.

    NaN IS MISSING DATA, AND IT MUST NOT REACH THE MODEL AS A NUMBER.
    `histogram_quantile` over a bucket with no observations returns NaN, which
    is the normal reading for a similarity or latency quantile during an
    outage: no requests happened, so there is no distribution to take a
    quantile of.

    Passing it through as `nan` cost a real misdiagnosis. On the first live F01
    run llama3.2 was shown `retrieval_top_similarity_p50 = nan` and reported
    "EV-M01 shows similarity at 0.658 which is healthy" - reciting this
    project's own documented baseline rather than reading the evidence - then
    ruled out F01 with "EV-M06 shows llm_error_ratio 0.0" when EV-M06 was 1.0,
    and diagnosed F06 at 0.9 confidence against a real endpoint outage. The
    deterministic cross-check refused it.

    A value the model cannot reason about is an invitation to supply one from
    memory, so this collapses NaN into the same `None` that a missing series
    already produced, and says so in the note.
    """
    if value is None or value != value:  # NaN is the only x != x
        return None, NO_DATA_NOTE
    return round(value, 4), ""


def collect(
    client: TargetClient,
    prometheus_url: str,
    promql: Callable[[str, str], float | None],
    fast_result: FastVerificationResult,
    baseline_rerank_threshold: float | None = None,
    backend_container: str = "rag_backend",
    include_logs: bool = True,
) -> EvidenceFrame:
    """Build the frame from the live system."""
    frame = EvidenceFrame(
        collected_at=datetime.now(UTC).isoformat(timespec="seconds")
    )

    # --- service identity, FIRST.
    # Without this the frame never names a service, so the model has to invent
    # one. A real run produced service="RAG", which validation correctly
    # rejected - but the gap was here, not in the model.
    frame.add(
        eid="EV-S01", kind="service", name="application_service",
        value="backend",
        note="the FastAPI service that serves /v1/chat and owns retrieval; "
             "use this exact name when the fault is in the application",
    )
    frame.add(
        eid="EV-S02", kind="service", name="declared_services",
        value="backend, db, frontend, toxiproxy, prometheus",
        note="the only valid values for the service field",
    )

    # --- metrics
    for n, (name, expr) in enumerate(METRIC_QUERIES.items(), start=1):
        value, note = reading(promql(prometheus_url, expr))
        frame.add(
            eid=f"EV-M{n:02d}", kind="metric", name=name, value=value,
            expected=HEALTHY_EXPECTATION.get(name, ""), note=note,
        )

    # --- current configuration
    try:
        cfg = client.config()
        settings = cfg.get("settings", {})
        for n, key in enumerate(
            ("rerank_threshold", "llm_model", "llm_base_url", "max_tokens",
             "chaos_enabled", "llm_timeout_s"), start=1
        ):
            frame.add(eid=f"EV-C{n:02d}", kind="config", name=key,
                      value=settings.get(key))
        frame.add(eid="EV-C07", kind="config", name="config_hash",
                  value=cfg.get("config_hash"))
        pv = (cfg.get("prompt_version") or {}).get("files", {})
        frame.add(eid="EV-C08", kind="config", name="prompt_file_hashes", value=pv)
    except TargetError as exc:
        frame.problems.append(f"could not read target config: {exc}")

    # --- the known-good value. Without it there is nothing to roll back TO.
    frame.add(
        eid="EV-B01", kind="baseline", name="baseline_rerank_threshold",
        value=baseline_rerank_threshold,
        note="captured known-good value; the repair restores this exact number",
    )

    # --- fast verification: the user-visible symptom
    frame.add(eid="EV-V00", kind="verification", name="fast_set_overall",
              value=f"{'PASS' if fast_result.passed else 'FAIL'} "
                    f"({fast_result.pass_rate:.0%} of cases)",
              expected="PASS (100%)")
    for n, c in enumerate(fast_result.cases, start=1):
        frame.add(
            eid=f"EV-V{n:02d}", kind="verification", name=f"fast_case_{c.case_id}",
            value=f"{'PASS' if c.passed else 'FAIL'} "
                  f"keyword={c.keyword_present} non_refusal={c.non_refusal} "
                  f"grounded={c.sources_block} {c.latency_s:.1f}s",
            expected="PASS with keyword present, non-refusal, and a Sources block",
            note="grounded=False means the answer carried no retrieved context",
        )

    # --- health
    frame.add(eid="EV-H01", kind="health", name="healthz",
              value=("ok" if fast_result.health_ok else "unhealthy")
                    + (f" ({fast_result.health_detail})" if fast_result.health_detail else ""),
              expected="ok with database and ollama both ok")

    # --- recent logs, user content removed
    if include_logs:
        for n, line in enumerate(_recent_logs(backend_container), start=1):
            frame.add(eid=f"EV-L{n:02d}", kind="log", name="backend_log", value=line)

    return frame
