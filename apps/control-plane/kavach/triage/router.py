from laya import Router


def classify_alert(alert_text: str) -> str:
    """
    Classifies a raw alert text into a high-level incident domain.
    """
    router = Router()
    
    questions = {
        "domain": {
            "type": "choice",
            "instructions": "Classify this IT alert into its primary domain category.",
            "criteria": {
                "database": "SQL errors, connection pool exhausted, slow queries",
                "network": "Connection refused, DNS timeout, TLS handshake failed",
                "application": "Null pointer, out of memory, unhandled exception, syntax error",
                "unknown": "Vague errors, generic 500s without trace"
            }
        }
    }
    
    result = router.predict(f"Alert: {alert_text}", questions)
    
    # Using Laya's returned choice key (e.g. 'database', 'network')
    return result["answers"]["domain"].get("choice", "unknown")
