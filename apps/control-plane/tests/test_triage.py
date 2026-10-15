import pytest

# Real Laya inference. Slow whenever a large model is resident in Ollama,
# and these are the tests whose subject IS the decision model, so they
# cannot be stubbed. Deselect with -m 'not laya'.
pytestmark = pytest.mark.laya

from kavach.triage.router import classify_alert


def test_triage_database() -> None:
    alert = "FATAL: remaining connection slots are reserved for non-replication superuser connections"
    domain = classify_alert(alert)
    assert domain == "database"


def test_triage_network() -> None:
    alert = "requests.exceptions.ConnectionError: HTTPConnectionPool(host='api', port=80): Max retries exceeded"
    domain = classify_alert(alert)
    assert domain == "network"


def test_triage_application() -> None:
    alert = "java.lang.NullPointerException at com.app.billing.InvoiceService.calculateTotal"
    domain = classify_alert(alert)
    assert domain == "application"
