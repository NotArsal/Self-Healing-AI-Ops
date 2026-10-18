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

import hashlib
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
    # The prompt files' CONTENTS, not just their digests. `prompt_version`
    # above is what the target reports over HTTP - sha256 prefixes - and a
    # digest cannot be rolled back to. `rollback_prompt` needs the bytes, and
    # this is the only place a known-good copy of them is recorded.
    #
    # Read from disk at capture time rather than over the control interface,
    # because the target exposes no endpoint that returns prompt text and
    # adding one would be a twelfth permitted addition (PRD.md 5.2). Capture
    # is a host operation with the repository present, so disk is available
    # here and is not available to the API - which is exactly why the API
    # mounts `harness/baselines/` read-only.
    prompt_contents: dict[str, str] = field(default_factory=dict)
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
            # A digest with no captured text cannot be rolled back to, so the
            # rendering says which of the two this is rather than implying a
            # usable known-good exists.
            held = len(self.prompt_contents.get(name, ""))
            note = f"{held}B held" if held else "NO CONTENT CAPTURED"
            lines.append(f"  prompt {name:<22} {digest}  ({note})")
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


def _capture_prompts(
    target: Path, declared_dir: str, reported_digests: dict[str, Any],
) -> tuple[dict[str, str], list[str]]:
    """Read the prompt files and check them against the target's own digests.

    Returns ({name: text}, problems). A file whose on-disk bytes hash to
    something other than what the running target reports is NOT captured: a
    known-good the target never served is worse than none, because the repair
    would write it confidently.
    """
    contents: dict[str, str] = {}
    problems: list[str] = []
    seen: set[str] = set()
    d = (target / declared_dir).resolve()
    if not d.is_dir():
        return contents, [f"prompt directory not found: {d}"]

    for path in sorted(d.glob("*.txt")):
        seen.add(path.name)
        try:
            raw = path.read_bytes()
        except OSError as exc:
            problems.append(f"could not read prompt {path.name}: {exc}")
            continue
        digest = hashlib.sha256(raw).hexdigest()[:12]
        reported = reported_digests.get(path.name)
        if reported is None:
            problems.append(
                f"prompt {path.name} is on disk but the target does not report "
                f"it; the running container is reading a different directory"
            )
            continue
        if reported != digest:
            problems.append(
                f"prompt {path.name} on disk hashes to {digest} but the target "
                f"reports {reported}; not captured, because a known-good the "
                f"target never served cannot be rolled back to"
            )
            continue
        contents[path.name] = raw.decode("utf-8")

    for name in sorted(set(reported_digests) - seen):
        problems.append(
            f"the target reports prompt {name} but there is no such file in "
            f"{d}; its known-good text cannot be captured"
        )
    return contents, problems


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

    # Prompt text, from disk. `rollback_prompt`'s inverse is a recorded value
    # like every other inverse in this system, and for prompts the recorded
    # value has to be the bytes - a digest restores nothing.
    #
    # Verified against the digests the TARGET reported above, not trusted. The
    # repository on disk and the directory bind-mounted into the running
    # container are two different things, and capturing bytes from a checkout
    # that the backend is not actually reading would record a known-good that
    # was never good for this target. A mismatch is a problem, not a warning.
    bl.prompt_contents, prompt_problems = _capture_prompts(
        target, manifest.versioned_paths.get("prompts", "./prompts"),
        (bl.prompt_version.get("files") or {}),
    )
    bl.problems.extend(prompt_problems)

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


# --- CLI ---------------------------------------------------------------------
#
# `make onboard` is the documented way to capture a baseline (`AGENTS.md`,
# `PRD.md` §5.1) and until 2026-10-17 the Makefile target printed "Not
# implemented until P1" and exited 1. It had been stale since P1 shipped the
# capture itself; nobody noticed because every caller so far was a test or a
# harness importing `capture()` directly.
#
# F07 is what forced it: `rollback_prompt` restores the prompt text recorded
# in `prompt_contents`, which only a capture taken after that field existed
# contains. The documented command for the thing a fault class depends on
# cannot be one that exits 1.
#
# A `__main__` here rather than a new `capture_cli.py` module: `capture()`
# and `save()` already exist and take their configuration from `Settings`,
# so the entry point is argument plumbing and nothing else.


def main(argv: list[str] | None = None) -> int:
    """Capture a baseline against the configured target and save it."""
    import argparse

    from kavach.config import get_settings

    settings = get_settings()
    ap = argparse.ArgumentParser(
        prog="python -m kavach.onboarding.baseline",
        description="Capture a last-known-good baseline from the live target.",
    )
    ap.add_argument("--target-path", default=settings.target_path)
    ap.add_argument("--prometheus", default=settings.prometheus_url)
    ap.add_argument("--chat-url", default=settings.target_chat_url)
    ap.add_argument("--admin-url", default=settings.target_config_url)
    ap.add_argument("--out", default=str(settings.baselines_dir()),
                    help="directory for the artifact; one file per capture")
    ap.add_argument(
        "--force", action="store_true",
        help="save even when the capture is not healthy. Refused by default: "
             "a baseline taken while a probe is failing makes every later "
             "comparison inherit the fault as normal",
    )
    args = ap.parse_args(argv)

    bl = capture(
        target_path=args.target_path,
        prometheus_url=args.prometheus,
        kavach_root=settings.root(),
        chat_url=args.chat_url,
        admin_url=args.admin_url,
        admin_token=settings.target_admin_token,
    )
    print(bl.render(), flush=True)
    print(flush=True)

    if not bl.healthy and not args.force:
        print("NOT HEALTHY - refusing to save. A baseline captured while a "
              "fast-verification case is failing is worse than no baseline, "
              "because every later comparison inherits the fault as normal. "
              "Fix the target, or pass --force if you know why.")
        return 1

    path = save(bl, args.out)
    held = {name: len(text) for name, text in bl.prompt_contents.items()}
    print(f"saved   {path}")
    print(f"prompts {held or 'NONE CAPTURED - rollback_prompt cannot be built'}")
    if not bl.healthy:
        print("WARNING: saved an UNHEALTHY capture because --force was given.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
