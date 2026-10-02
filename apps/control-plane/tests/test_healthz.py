"""Phase 0 acceptance: /healthz returns 200."""

from fastapi.testclient import TestClient

from kavach.main import create_app


def test_healthz_returns_200() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_default_mode_is_simulation() -> None:
    """PRD.md §5.4 and AGENTS.md security rule 5.

    This is not a style assertion. If the shipped default ever becomes
    AUTONOMOUS, a freshly onboarded project would be eligible for automatic
    writes before anyone had reviewed its allow-list.
    """
    client = TestClient(create_app())

    assert client.get("/healthz").json()["default_mode"] == "SIMULATION"
