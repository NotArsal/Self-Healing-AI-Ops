from kavach.evaluation.log_filter import filter_logs


def test_log_filter():
    context = "Database connection pool exhaustion"
    
    irrelevant_logs = "INFO: 200 GET /healthz\nINFO: user login successful"
    relevant_logs = "ERROR: connection pool empty\nFATAL: too many connections for role"
    
    irrelevant_score = filter_logs(irrelevant_logs, context)
    relevant_score = filter_logs(relevant_logs, context)
    
    assert relevant_score > irrelevant_score
    assert irrelevant_score < 5.0
    assert relevant_score > 5.0
