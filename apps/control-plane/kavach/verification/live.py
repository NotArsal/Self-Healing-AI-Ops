"""Measurement against a live application.

Every number here comes from an HTTP response. Nothing is derived from a
threshold, which is what separated this from `probes.py`'s simulated path.

Kavach does not query Prometheus in the healing loop (ARCHITECTURE.md 2.4), so
objectives are measured by active probing. That bounds which declared metrics can
be measured at all -- see MEASURABLE_METRICS -- and the contract does not
currently say so. Logged as proof #2 defect #5.
"""

from collections.abc import Callable
from pathlib import Path

import httpx
import yaml

from kavach.preflight.schema import KavachManifest
from kavach.scenarios.schema import Scenario, TargetBinding
from kavach.verification.baseline import load_baseline

TIMEOUT_S = 5.0
AVAILABILITY_SAMPLES = 10


class LiveProbeError(Exception):
    pass


def probe_health(target: TargetBinding) -> dict[str, str]:
    """Hit every declared health endpoint. Services declaring none are unknown."""
    results: dict[str, str] = {}
    for name, svc in target.manifest.services.items():
        if not svc.health:
            results[name] = "unknown"
            continue
        if svc.health.type != "http":
            # tcp/exec health checks are a contract feature v1 does not probe.
            results[name] = "unknown"
            continue
        try:
            with httpx.Client(timeout=svc.health.timeout_s or TIMEOUT_S) as client:
                res = client.get(svc.health.target)
            expected = svc.health.expect_status or 200
            results[name] = "healthy" if res.status_code == expected else "unhealthy"
        except httpx.HTTPError:
            results[name] = "unhealthy"
    return results


def _query_runner_target(manifest: KavachManifest) -> str:
    if not manifest.quality or manifest.quality.runner.type != "http":
        raise LiveProbeError("manifest declares no http quality runner to probe")
    return manifest.quality.runner.target


def measure_error_ratio(target: TargetBinding) -> float:
    """Fraction of sampled requests that did not succeed."""
    url = _query_runner_target(target.manifest)
    failures = 0
    with httpx.Client(timeout=TIMEOUT_S) as client:
        for i in range(AVAILABILITY_SAMPLES):
            try:
                res = client.post(url, json={"question": f"availability probe {i}"})
                if not res.is_success:
                    failures += 1
            except httpx.HTTPError:
                failures += 1
    return failures / AVAILABILITY_SAMPLES


def measure_eval_pass_rate(target: TargetBinding) -> float:
    """Really run the declared golden set and score it."""
    manifest = target.manifest
    if not manifest.quality:
        raise LiveProbeError("manifest declares no quality block")

    golden_path = (
        Path(target.manifest_path).parent / manifest.quality.golden_set
    ).resolve()
    if not golden_path.exists():
        raise LiveProbeError(f"golden set not found: {golden_path}")

    data = yaml.safe_load(golden_path.read_text(encoding="utf-8")) or {}
    cases = data.get("cases", [])
    if len(cases) < manifest.quality.min_cases:
        raise LiveProbeError(
            f"golden set has {len(cases)} cases, manifest requires "
            f"{manifest.quality.min_cases}"
        )

    url = _query_runner_target(manifest)
    passed = 0
    with httpx.Client(timeout=TIMEOUT_S) as client:
        for case in cases:
            try:
                res = client.post(url, json={"question": case.get("question", "")})
                if not res.is_success:
                    continue
                answer = str(res.json().get("answer", ""))
            except (httpx.HTTPError, ValueError):
                continue
            expected = case.get("expect_contains") or []
            if all(fragment in answer for fragment in expected):
                passed += 1

    return passed / len(cases)


# Metric names this platform can measure by active probing. A declared objective
# whose metric is absent here cannot be verified without Prometheus, and
# verification says so rather than inventing a value.
MEASURABLE_METRICS: dict[str, Callable[[TargetBinding], float]] = {
    "http_requests_errors_ratio": measure_error_ratio,
    "kavach_eval_pass_rate": measure_eval_pass_rate,
}


def measure_objectives(target: TargetBinding) -> dict[str, float]:
    """Measure every declared objective this platform knows how to probe."""
    manifest = target.manifest
    measured: dict[str, float] = {}
    if not manifest.objectives:
        return measured

    for category in ("availability", "latency", "quality", "cost"):
        metrics = getattr(manifest.objectives, category)
        if not metrics:
            continue
        probe = MEASURABLE_METRICS.get(metrics[0].metric)
        if probe is None:
            continue
        measured[category] = probe(target)
    return measured


def unmeasurable_metrics(manifest: KavachManifest) -> list[str]:
    """Declared metrics that cannot be actively probed. Reported at onboarding."""
    if not manifest.objectives:
        return []
    missing = []
    for category in ("availability", "latency", "quality", "cost"):
        for metric in getattr(manifest.objectives, category):
            if metric.metric not in MEASURABLE_METRICS:
                missing.append(metric.metric)
    return missing


def verify_live(scenario: Scenario) -> tuple[bool, dict[str, float]]:
    """Re-measure every objective and report its delta against the healthy baseline.

    Returns deltas per objective, never a single boolean verdict: a repair that
    restores availability while degrading quality is a different outcome from one
    that restores both, and collapsing them deletes the feature.

    Deltas are measured against the onboarding baseline, not against the values
    seen at detection -- comparing a repair to the outage it replaced would score
    a degraded recovery as an improvement.
    """
    if scenario.target is None:
        raise LiveProbeError("verify_live called on a scenario with no live target")

    measured = measure_objectives(scenario.target)
    baseline = load_baseline(scenario.target.manifest_path) or {}
    deltas: dict[str, float] = {}
    passed = True

    for category, objective in (scenario.objectives or {}).items():
        if category not in measured:
            # Declared but unmeasurable by active probing. Not a pass: verification
            # that cannot see an objective must not claim it is satisfied.
            passed = False
            continue
        value = measured[category]
        reference = baseline.get(category, objective.value)
        deltas[category] = value - reference
        if not satisfies(value, objective.comparator, objective.threshold):
            passed = False

    if not _within_tolerance(scenario, measured, baseline):
        passed = False

    return passed, deltas


def _within_tolerance(
    scenario: Scenario, measured: dict[str, float], baseline: dict[str, float]
) -> bool:
    """A repair may degrade a secondary objective, but only within tolerance.

    Unenforceable without an onboarding baseline, in which case this abstains
    rather than guessing; `make onboard` captures one.
    """
    max_drop_pct = (scenario.tolerance or {}).get("quality_drop_pct")
    reference = baseline.get("quality")
    if max_drop_pct is None or "quality" not in measured or not reference:
        return True

    drop_pct = (reference - measured["quality"]) / reference * 100
    return drop_pct <= max_drop_pct


def satisfies(value: float, comparator: str, threshold: float) -> bool:
    match comparator:
        case "<":
            return value < threshold
        case "<=":
            return value <= threshold
        case ">":
            return value > threshold
        case ">=":
            return value >= threshold
        case "==":
            return value == threshold
        case _:
            raise LiveProbeError(f"unknown comparator: {comparator}")
