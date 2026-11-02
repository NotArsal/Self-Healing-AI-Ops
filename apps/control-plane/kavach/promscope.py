"""Scope a PromQL expression to one project, or leave it exactly as it was.

THE BUG THIS EXISTS FOR, found 2026-11-03 by onboarding a second target.
Every PromQL expression in the detectors and the evidence frame names a metric
without saying which application it belongs to. With one target running that
is unambiguous. With two, Prometheus holds two correctly-labelled series and
`result[0]` picks whichever came back first:

    project=simple-rag  ragapp_corpus_chunks = 30
    project=lightrag    ragapp_corpus_chunks = 2

`check_corpus_fingerprint` read 30 while checking the second target, and
reported that its corpus had drifted. Auditing every query: they filter on
`operation` and `outcome` and not one carries a `project` or `job` selector.
So Kavach as built supports exactly one target at a time
(`docs/SECOND_TARGET.md`).

WHY THIS IS OPT-IN, AND WHY THAT MATTERS MORE THAN THE FIX
Those expressions are the instrument every number in `REPORT_DRAFT.md` §4 was
measured with, including the `[2m]` and `[10m]` windows that ADR 0010 and ADR
0013 argued over. Changing what they mean would put 80 injections' worth of
measurement in doubt, and a bench run costs eight hours.

So `scope("", expr)` returns `expr` **byte-identical**, and
`test_promscope.py` asserts that against every expression in all three query
dictionaries. Nothing changes for the existing target until a manifest asks
for it. The fix is available; the measurements are not disturbed.

WHAT IT MATCHES, AND WHAT IT DELIBERATELY DOES NOT
Only identifiers beginning `ragapp_` or `http_` - the two prefixes the target
contract uses. PromQL functions and keywords (`sum`, `rate`, `clamp_min`,
`histogram_quantile`, `vector`, `le`) are left alone because none of them
starts with either prefix. A regex that tried to scope "every identifier"
would corrupt `sum by (le)`.
"""

from __future__ import annotations

import re

# The metric prefixes a target may export. `ragapp_` is the application's own
# contract; `http_` comes from prometheus-fastapi-instrumentator and carries
# the `chat_*` SLO signals. Anything else in an expression is PromQL syntax.
TARGET_METRIC_PREFIXES = ("ragapp_", "http_")

_SELECTOR = re.compile(
    r"\b((?:" + "|".join(TARGET_METRIC_PREFIXES) + r")[A-Za-z0-9_]*)"
    r"(?:\{(?P<labels>[^}]*)\})?"
)

# A project name goes inside a PromQL string literal, so it must not be able
# to close that literal or inject another matcher. Prometheus label values are
# arbitrary UTF-8, but a manifest project name that needed escaping would be a
# different problem; refusing is safer than quoting.
_SAFE_PROJECT = re.compile(r"^[A-Za-z0-9_.:-]+$")


class UnsafeProjectNameError(ValueError):
    """The project name cannot be embedded in a PromQL label matcher."""


def scope(project: str, expr: str, label: str = "project") -> str:
    """Return `expr` with `{label="project"}` on every target metric selector.

    `project=""` returns `expr` unchanged, byte for byte. That is the default
    everywhere and the reason this can land without re-measuring anything.

    A selector that already constrains `label` is left alone, so applying this
    twice is a no-op rather than producing a contradictory matcher.
    """
    if not project:
        return expr
    if not _SAFE_PROJECT.match(project):
        raise UnsafeProjectNameError(
            f"project name {project!r} is not safe to embed in a PromQL label "
            f"matcher; allowed characters are letters, digits, and . : _ -")

    matcher = f'{label}="{project}"'

    def rewrite(m: re.Match[str]) -> str:
        name = m.group(1)
        labels = m.group("labels")
        if labels is None:
            return f"{name}{{{matcher}}}"
        if re.search(rf"\b{re.escape(label)}\s*(=|!=|=~|!~)", labels):
            # Already constrained on this label - do not add a second,
            # contradictory matcher.
            return m.group(0)
        inner = labels.strip()
        return f"{name}{{{inner},{matcher}}}" if inner else f"{name}{{{matcher}}}"

    return _SELECTOR.sub(rewrite, expr)


def scope_all(project: str, queries: dict[str, str],
              label: str = "project") -> dict[str, str]:
    """`scope` over a whole query dictionary, preserving key order."""
    return {k: scope(project, v, label) for k, v in queries.items()}


def _demo() -> None:
    """Runnable check: `python -I kavach/promscope.py`.

    The first assertion is the one that matters - it is the promise that this
    module changes nothing until asked.
    """
    from kavach.detection.endpoint_outage import QUERIES as F01
    from kavach.detection.retrieval_collapse import QUERIES as F06
    from kavach.rca.evidence import METRIC_QUERIES as FRAME

    for name, d in (("F01", F01), ("F06", F06), ("frame", FRAME)):
        for key, expr in d.items():
            assert scope("", expr) == expr, f"{name}.{key} changed when unscoped"

    assert (scope("simple-rag", "ragapp_corpus_chunks")
            == 'ragapp_corpus_chunks{project="simple-rag"}')
    assert (scope("x", 'ragapp_llm_requests_total{outcome!="ok"}[2m]')
            == 'ragapp_llm_requests_total{outcome!="ok",project="x"}[2m]')
    # Functions and the `le` grouping label must survive untouched.
    before = "histogram_quantile(0.50, sum by (le) (rate(ragapp_x_bucket[10m])))"
    after = scope("p", before)
    assert "sum by (le)" in after and "histogram_quantile(0.50," in after
    assert 'ragapp_x_bucket{project="p"}[10m]' in after
    # Idempotent.
    assert scope("p", after) == after, "applying scope twice changed the query"
    # Unsafe names refused rather than quoted.
    try:
        scope('a" or up{', "ragapp_x")
    except UnsafeProjectNameError:
        pass
    else:  # pragma: no cover
        raise AssertionError("an injectable project name was accepted")

    total = len(F01) + len(F06) + len(FRAME)
    print(f"promscope self-check OK - {total} expressions unchanged when "
          f"unscoped, 4 rewrite cases, idempotent, injection refused")


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path[:0] = [str(Path(__file__).resolve().parents[1])]
    _demo()
