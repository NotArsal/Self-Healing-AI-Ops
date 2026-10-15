"""Test isolation from the knowledge base.

`diagnose_node` and `outcome_node` reach Postgres and Ollama directly, through
`asyncio.run()` inside sync graph nodes. While the database credentials were
wrong those calls failed instantly into a bare `except` and the unit tests never
noticed. Once the credentials were fixed and F-MEM started working, every test
that drives the graph began making real embedding and database calls -- a single
one took over two minutes, and `make test` stopped finishing at all.

Unit tests should not depend on a running database or model, so the knowledge
base is stubbed for the whole suite. This is isolation, not a behaviour change:
nothing here asserts on knowledge-base contents.

F-MEM therefore has no automated coverage. It was verified by hand against a
real Postgres and real embeddings (an incident stored, then recalled by
similarity with its repair action). A proper test needs a database fixture and is
worth adding.

The real fix is for graph nodes not to open event loops or talk to I/O directly;
see the asyncio.run() calls in kavach/graph/nodes.py.
"""

import pytest

# Modules whose subject *is* the decision model; they must see the real thing.
# test_p5_safety is deliberately not here: it asserts on permit() verdicts, and
# the Laya call in gate_node is incidental to what it checks.
LAYA_UNDER_TEST = {"test_tnr_gate", "test_triage"}


@pytest.fixture(autouse=True)
def _stub_shadow_laya(request, monkeypatch):
    """Keep real Laya inference out of tests that are not about Laya.

    gate_node consults Laya on every action. It is advisory and cannot change a
    verdict (AGENTS.md: shadow only), but each call is a local transformer
    inference, and an unwind loop makes four. With a 7B model resident in Ollama
    these crawl: one graph test took over two minutes, which is why the suite
    appeared to hang whenever the services were up. tests/test_debt.py already
    stubbed it per-file; this does it for the suite.
    """
    if request.node.module.__name__.split(".")[-1] in LAYA_UNDER_TEST:
        return
    if request.node.get_closest_marker("live"):
        return  # the live suite stubs it in its own fixture

    from kavach.remediation.tnr_gate import SafetyAssessment

    monkeypatch.setattr(
        "kavach.remediation.tnr_gate.evaluate_safety",
        lambda action, context: SafetyAssessment(is_safe=True, reason="stubbed"),
    )


@pytest.fixture(autouse=True)
def _isolate_knowledge_base(request, monkeypatch):
    """Stop graph tests making real embedding and database calls."""
    # The live suite drives a real application on purpose; leave it alone.
    if request.node.get_closest_marker("live"):
        return

    async def _no_similar_incidents(*args, **kwargs):
        return []

    async def _no_save(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "kavach.knowledge.retrieval.retrieve_similar_incidents",
        _no_similar_incidents,
    )
    monkeypatch.setattr(
        "kavach.knowledge.store.save_incident_memory", _no_save
    )
