"""Baseline capture — what "last-known-good" means, as data.

Everything downstream compares against this: an SLO threshold is only
meaningful relative to a measured healthy value, and a verification result is
only meaningful relative to a verification that passed when nothing was wrong.

Three properties this module is built around:

1. **Read-only.** Capture runs the fast-verification questions through the
   target's normal query path and reads its metrics and config. It writes
   nothing to the target. The corpus fingerprint is captured before and after
   and compared, so a capture that *did* mutate the corpus fails loudly rather
   than silently recording a changed system as the baseline.

2. **Repeatable.** Capture can be run any number of times; each run is a
   separate artifact. Two runs of a healthy system should agree, and
   disagreement is information.

3. **Refuses to record an unhealthy baseline.** A baseline captured while a
   fast-verification case is failing is worse than no baseline, because every
   later comparison inherits the fault as "normal".
"""

from __future__ import annotations

import json
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from kavach.onboarding.manifest import Manifest, load

REFUSAL_MARKERS = ("don't know", "do not know", "no mention", "don't have any documents")
SOURCES_MARKER = "**sources:**"


@dataclass
class CaseMeasurement:
    case_id: str
    question: str
    expected_keyword: str
    keyword_present: bool
    non_refusal: bool
    sources_block: bool
    latency_s: float

    @property
    def passed(self) -> bool:
        return self.keyword_present and self.non_refusal and self.sources_block


@dataclass
class Baseline:
    captured_at: str
    project: str
    healthy: bool
    # Fast verification
    cases: list[CaseMeasurement] = field(default_factory=list)
    fast_set_total_s: float = 0.0
    fast_set_pass_rate: float = 0.0
    # Target identity and configuration
    config_hash: str = ""
    prompt_version: dict[str, Any] = field(default_factory=dict)
    corpus_fingerprint: dict[str, Any] = field(default_factory=dict)
    rerank_threshold: float | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    # SLO values at capture time
    slo_values: dict[str, float | None] = field(default_factory=dict)
    slo_satisfied: dict[str, bool | None] = field(default_factory=dict)
    # Supporting metric snapshot
    metrics: dict[str, float | None] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def render(self) -> str:
        lines = [
            f"Baseline: {self.project}",
            f"Captured: {self.captured_at}",
            f"Healthy:  {'YES' if self.healthy else 'NO - NOT USABLE AS A BASELINE'}",
            "",
            "Fast verification "
            f"({self.fast_set_pass_rate:.0%} pass, {self.fast_set_total_s:.1f}s serial)",
        ]
        for c in self.cases:
            lines.append(
                f"  [{'PASS' if c.passed else 'FAIL'}] {c.case_id}  {c.latency_s:5.1f}s  "
                f"kw={c.expected_keyword!r} present={c.keyword_present} "
                f"grounded={c.sources_block}"
            )
        lines += ["", "Identity"]
        lines.append(f"  config_hash       {self.config_hash}")
        lines.append(f"  rerank_threshold  {self.rerank_threshold}")
        lines.append(f"  corpus            {self.corpus_fingerprint}")
        for name, digest in (self.prompt_version.get("files") or {}).items():
            lines.append(f"  prompt {name:<22} {digest}")
        lines += ["", "SLO values at capture"]
        for name, value in self.slo_values.items():
            ok = self.slo_satisfied.get(name)
            mark = "ok " if ok else ("BREACH" if ok is False else "?")
            shown = "none" if value is None else f"{value:.4g}"
            lines.append(f"  [{mark:>6}] {name:<26} {shown}")
        lines += ["", "Metric snapshot"]
        for name, value in self.metrics.items():
            shown = "none" if value is None else f"{value:.4g}"
            lines.append(f"  {name:<34} {shown}")
        if self.problems:
            lines += ["", "Problems"]
            lines += [f"  - {p}" for p in self.problems]
        return "\n".join(lines)


# --- helpers ----------------------------------------------------------------


def _post_json(
    url: str, body: dict[str, Any], timeout: float,
    headers: dict[str, str] | None = None,
) -> Any:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _get_json(
    url: str, timeout: float, headers: dict[str, str] | None = None
) -> Any:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _promql(prometheus_url: str, expr: str, timeout: float = 10.0) -> float | None:
    """Evaluate an instant query. None means no series, which is NOT zero."""
    url = (f"{prometheus_url.rstrip('/')}/api/v1/query"
           f"?query={urllib.parse.quote(expr)}")
    try:
        payload = _get_json(url, timeout)
    except (urllib.error.URLError, TimeoutError):
        return None
    if payload.get("status") != "success":
        return None
    result = payload.get("data", {}).get("result", [])
    if not result:
        return None
    try:
        return float(result[0]["value"][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


_COMPARATORS = {
    "<": lambda v, t: v < t,
    "<=": lambda v, t: v <= t,
    ">": lambda v, t: v > t,
    ">=": lambda v, t: v >= t,
    "==": lambda v, t: v == t,
}


def _corpus_fingerprint(prometheus_url: str) -> dict[str, Any]:
    """Read the corpus size from metrics rather than the database.

    Deliberately not a psql call: Kavach has the docker socket, and shelling
    into a container to run SQL would be an arbitrary-execution path. The
    target exports the counts, so they are read like any other metric.
    """
    return {
        "chunks": _promql(prometheus_url, "ragapp_corpus_chunks"),
        "files": _promql(prometheus_url, "ragapp_corpus_files"),
    }


SNAPSHOT_METRICS = {
    "llm_requests_ok": 'sum(ragapp_llm_requests_total{outcome="ok"}) or vector(0)',
    "llm_requests_error": 'sum(ragapp_llm_requests_total{outcome="error"}) or vector(0)',
    "llm_tokens_total": "sum(ragapp_llm_tokens_total) or vector(0)",
    "retrieval_similarity_p50": (
        "histogram_quantile(0.50, sum by (le) "
        "(rate(ragapp_retrieval_top_similarity_bucket[30m])))"
    ),
    "empty_context_total": "sum(ragapp_retrieval_empty_context_total) or vector(0)",
    "db_pool_in_use": "max(ragapp_db_pool_in_use)",
    "db_pool_max": "max(ragapp_db_pool_max)",
    "corpus_chunks": "ragapp_corpus_chunks",
    "corpus_files": "ragapp_corpus_files",
}


# --- capture ----------------------------------------------------------------


def capture(
    target_path: str | Path,
    prometheus_url: str,
    kavach_root: str | Path,
    chat_url: str = "http://localhost:8000/v1/chat",
    admin_url: str = "http://localhost:8000/v1/admin/config",
    admin_token: str = "",
) -> Baseline:
    """Measure a healthy target. Writes nothing to it."""
    target = Path(target_path)
    manifest: Manifest = load(target / "kavach.yaml")

    bl = Baseline(
        captured_at=datetime.now(UTC).isoformat(timespec="seconds"),
        project=manifest.project.name,
        healthy=False,
    )

    # Corpus fingerprint BEFORE, so mutation during capture is detectable.
    corpus_before = _corpus_fingerprint(prometheus_url)

    # Target configuration and prompt identity.
    headers = {"X-Admin-Token": admin_token} if admin_token else {}
    try:
        cfg = _get_json(admin_url, 15.0, headers)
        bl.config_hash = cfg.get("config_hash", "")
        bl.prompt_version = cfg.get("prompt_version", {})
        bl.settings = cfg.get("settings", {})
        bl.rerank_threshold = bl.settings.get("rerank_threshold")
    except Exception as exc:
        bl.problems.append(f"could not read target config: {exc}")

    # The fast-verification set, run exactly as the live loop runs it: the same
    # 3 cases, serially, so the numbers are comparable to a later run.
    fast_set_path = _resolve_fast_set(manifest, Path(kavach_root))
    if fast_set_path is None:
        bl.problems.append(f"fast set not found: {manifest.verification.fast.set}")
        return bl

    doc = yaml.safe_load(fast_set_path.read_text(encoding="utf-8"))
    cases = doc.get("cases", [])
    if len(cases) != 3:
        bl.problems.append(f"fast set declares {len(cases)} cases, expected 3")

    set_started = time.perf_counter()
    for case in cases:
        q = case["question"]
        kw = str(case["expected_keyword"])
        t0 = time.perf_counter()
        try:
            answer = _post_json(chat_url, {"question": q}, 240.0)["answer"]
        except Exception as exc:
            bl.problems.append(f"{case['id']}: request failed: {exc}")
            bl.cases.append(CaseMeasurement(
                case["id"], q, kw, False, False, False, time.perf_counter() - t0))
            continue
        low = answer.lower()
        bl.cases.append(CaseMeasurement(
            case_id=case["id"], question=q, expected_keyword=kw,
            keyword_present=kw.lower() in low,
            non_refusal=not any(m in low for m in REFUSAL_MARKERS),
            sources_block=SOURCES_MARKER in low,
            latency_s=time.perf_counter() - t0,
        ))
    bl.fast_set_total_s = time.perf_counter() - set_started
    if bl.cases:
        bl.fast_set_pass_rate = sum(c.passed for c in bl.cases) / len(bl.cases)

    # SLO values as measured now. These are what provisional thresholds get
    # re-based against.
    for slo in manifest.slo:
        value = _promql(prometheus_url, slo.expression)
        bl.slo_values[slo.name] = value
        if value is None:
            bl.slo_satisfied[slo.name] = None
            bl.problems.append(f"SLO {slo.name!r} returned no series")
        else:
            bl.slo_satisfied[slo.name] = _COMPARATORS[slo.comparator](value, slo.threshold)

    for name, expr in SNAPSHOT_METRICS.items():
        bl.metrics[name] = _promql(prometheus_url, expr)

    # Corpus fingerprint AFTER. Capture must not have changed it.
    corpus_after = _corpus_fingerprint(prometheus_url)
    bl.corpus_fingerprint = corpus_after
    if corpus_before != corpus_after:
        bl.problems.append(
            f"CORPUS MUTATED DURING CAPTURE: {corpus_before} -> {corpus_after}. "
            "Baseline capture must be read-only; this artifact is not usable."
        )

    declared = (manifest.baseline.corpus_fingerprint if manifest.baseline else None)
    if declared is not None and (
        corpus_after.get("chunks") != declared.chunks
        or corpus_after.get("files") != len(declared.files)
    ):
        bl.problems.append(
            f"corpus does not match the manifest: live {corpus_after}, "
            f"declared chunks={declared.chunks} files={len(declared.files)}"
        )

    # A baseline is only usable if the system was healthy when it was taken.
    all_passed = bool(bl.cases) and all(c.passed for c in bl.cases)
    if not all_passed:
        bl.problems.append(
            "not every fast-verification case passed; a baseline taken from an "
            "unhealthy system would make the fault look normal forever after"
        )
    breached = [n for n, ok in bl.slo_satisfied.items() if ok is False]
    if breached:
        bl.problems.append(f"SLOs already breaching at capture: {breached}")

    bl.healthy = all_passed and not breached and corpus_before == corpus_after
    return bl


def _resolve_fast_set(manifest: Manifest, kavach_root: Path) -> Path | None:
    rel = manifest.verification.fast.set
    for candidate in (kavach_root / rel, kavach_root / "apps/control-plane" / rel):
        if candidate.is_file():
            return candidate
    return None


def save(bl: Baseline, directory: str | Path) -> Path:
    """Write the artifact. One file per capture; nothing is overwritten."""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    stamp = bl.captured_at.replace(":", "").replace("-", "")
    path = d / f"baseline-{bl.project}-{stamp}.json"
    path.write_text(json.dumps(bl.to_dict(), indent=2, sort_keys=False) + "\n",
                    encoding="utf-8")
    return path


def compare(old: Baseline, new: Baseline) -> list[str]:
    """Differences between two captures, for drift detection."""
    out: list[str] = []
    if old.config_hash != new.config_hash:
        out.append(f"config_hash {old.config_hash} -> {new.config_hash}")
    if old.prompt_version.get("files") != new.prompt_version.get("files"):
        out.append("prompt files changed")
    if old.corpus_fingerprint != new.corpus_fingerprint:
        out.append(f"corpus {old.corpus_fingerprint} -> {new.corpus_fingerprint}")
    if old.rerank_threshold != new.rerank_threshold:
        out.append(f"rerank_threshold {old.rerank_threshold} -> {new.rerank_threshold}")
    old_lat = statistics.mean([c.latency_s for c in old.cases]) if old.cases else 0
    new_lat = statistics.mean([c.latency_s for c in new.cases]) if new.cases else 0
    if old_lat and abs(new_lat - old_lat) / old_lat > 0.5:
        out.append(f"mean case latency {old_lat:.1f}s -> {new_lat:.1f}s")
    return out
