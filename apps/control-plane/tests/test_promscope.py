"""Project scoping must change nothing until it is asked for.

THE POINT OF THIS FILE is the first test. `promscope.scope` exists because
every PromQL expression in Kavach names a metric without saying which
application it belongs to, so two targets exporting the same contract make
every query ambiguous (`docs/SECOND_TARGET.md`). But those same expressions
are the instrument all 80 bench injections in `REPORT_DRAFT.md` §4 were
measured with, and a bench run costs eight hours.

So the fix is opt-in, and `test_every_query_is_untouched_when_unscoped` is the
assertion that makes it safe to land: with no project supplied, every query in
all three dictionaries comes back byte-identical. If that test ever fails,
the published measurements describe a system that no longer exists.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import pytest

from kavach.detection.endpoint_outage import QUERIES as F01_QUERIES
from kavach.detection.retrieval_collapse import QUERIES as F06_QUERIES
from kavach.promscope import (
    UnsafeProjectNameError,
    scope,
    scope_all,
)
from kavach.rca.evidence import METRIC_QUERIES

ALL_QUERIES = {
    "endpoint_outage": F01_QUERIES,
    "retrieval_collapse": F06_QUERIES,
    "evidence_frame": METRIC_QUERIES,
}

PROM = "http://localhost:9091"


def test_every_query_is_untouched_when_unscoped() -> None:
    """The safety promise. Do not relax this test; fix the code instead."""
    for group, queries in ALL_QUERIES.items():
        for key, expr in queries.items():
            assert scope("", expr) == expr, (
                f"{group}.{key} was modified with no project supplied. Every "
                f"quality number in the report was measured with the original "
                f"expression; changing it silently re-measures the system.")
            assert scope_all("", queries)[key] == expr


def test_a_bare_metric_gains_the_selector() -> None:
    assert (scope("simple-rag", "ragapp_corpus_chunks")
            == 'ragapp_corpus_chunks{project="simple-rag"}')


def test_existing_labels_are_preserved_not_replaced() -> None:
    """The F01 detector's numerator depends on `outcome!="ok"` surviving."""
    out = scope("lightrag", 'ragapp_llm_requests_total{outcome!="ok"}[2m]')
    assert out == 'ragapp_llm_requests_total{outcome!="ok",project="lightrag"}[2m]'


def test_promql_syntax_is_not_corrupted() -> None:
    """`sum by (le)` is the trap: a regex scoping "every identifier" would
    rewrite the grouping label and produce something Prometheus rejects."""
    before = ("histogram_quantile(0.50, sum by (le) "
              "(rate(ragapp_retrieval_top_similarity_bucket[10m])))")
    after = scope("p", before)
    assert "sum by (le)" in after
    assert "histogram_quantile(0.50," in after
    assert 'ragapp_retrieval_top_similarity_bucket{project="p"}[10m]' in after


def test_http_metrics_are_scoped_too() -> None:
    """`chat_error_ratio` reads `http_requests_total`, not a `ragapp_` name.
    Scoping only the application's own prefix would leave the SLO signals
    ambiguous while appearing to fix the problem."""
    out = scope("x", 'http_requests_total{handler="/v1/chat",status="5xx"}')
    assert out == ('http_requests_total{handler="/v1/chat",status="5xx",'
                   'project="x"}')


def test_scoping_is_idempotent() -> None:
    """Applied twice it must not produce two matchers on the same label, which
    would be a contradiction Prometheus evaluates to the empty set."""
    once = scope_all("p", METRIC_QUERIES)
    twice = scope_all("p", once)
    assert twice == once


def test_an_injectable_project_name_is_refused() -> None:
    """The name lands inside a PromQL string literal. A name that could close
    that literal is refused rather than quoted - a manifest needing escaping
    is a different problem from a manifest trying to inject a matcher."""
    for bad in ('a" or up{', "a}", 'x"', "a b", ""):
        if bad == "":
            # Empty is the documented no-op, not an error.
            assert scope(bad, "ragapp_x") == "ragapp_x"
            continue
        with pytest.raises(UnsafeProjectNameError):
            scope(bad, "ragapp_corpus_chunks")


def test_the_label_name_is_configurable_but_defaults_to_project() -> None:
    """The scrape configs label targets with `project`; `job` is the fallback
    if a deployment labels differently."""
    assert 'project="p"' in scope("p", "ragapp_x")
    assert 'job="p"' in scope("p", "ragapp_x", label="job")


@pytest.mark.docker
def test_every_scoped_query_is_accepted_by_a_real_prometheus() -> None:
    """A string that looks like PromQL is not necessarily PromQL.

    Each rewritten expression goes to the live Prometheus; a syntax error
    returns HTTP 400 with `status: error`, which no amount of string
    assertions above would have caught.
    """
    failures: list[str] = []
    for group, queries in ALL_QUERIES.items():
        for key, expr in scope_all("simple-rag", queries).items():
            url = (f"{PROM}/api/v1/query?query="
                   f"{urllib.parse.quote(expr)}")
            try:
                with urllib.request.urlopen(url, timeout=10) as r:
                    payload = json.load(r)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode(errors="replace")[:160]
                failures.append(f"{group}.{key}: HTTP {exc.code} {body}")
                continue
            except Exception as exc:
                pytest.skip(f"no reachable Prometheus at {PROM}: {exc}")
            if payload.get("status") != "success":
                failures.append(f"{group}.{key}: {payload.get('error')}")
    assert not failures, "Prometheus rejected scoped queries:\n" + "\n".join(
        failures)
