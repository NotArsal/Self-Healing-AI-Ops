from kavach.triage.router import classify_alert


def test_triage_database():
    alert = "FATAL: remaining connection slots are reserved for non-replication superuser connections"
    domain = classify_alert(alert)
    assert domain == "database"

def test_triage_network():
    alert = "requests.exceptions.ConnectionError: HTTPConnectionPool(host='api', port=80): Max retries exceeded"
    domain = classify_alert(alert)
    assert domain == "network"

def test_triage_application():
    alert = "java.lang.NullPointerException at com.app.billing.InvoiceService.calculateTotal"
    domain = classify_alert(alert)
    assert domain == "application"
