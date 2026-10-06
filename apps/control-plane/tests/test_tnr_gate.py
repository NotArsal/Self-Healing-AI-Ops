from kavach.remediation.tnr_gate import evaluate_safety


def test_tnr_gate_destructive():
    context = "Database CPU usage is at 99%"
    action = "rm -rf /var/lib/mysql"
    result = evaluate_safety(action, context)
    assert result.is_safe == False
    assert (
        "destructive" in result.reason.lower()
        or "high_risk" in result.reason.lower()
        or "medium_risk" in result.reason.lower()
    )


def test_tnr_gate_safe():
    context = "High network latency observed"
    action = "echo 'status is healthy'"
    result = evaluate_safety(action, context)
    # Ping should be completely safe
    assert result.is_safe == True


def test_tnr_gate_restart_service():
    context = "Service is hanging"
    action = "systemctl restart payment-service"
    result = evaluate_safety(action, context)
    # Restarting a service is typically considered destructive or medium/high risk
    assert result.is_safe == False
