from laya import Router


def filter_logs(logs_text: str, incident_context: str) -> float:
    """
    Scores a chunk of logs from 1 to 10 on its relevance to the incident.
    Returns the float score.
    """
    router = Router()
    
    questions = {
        "relevance": {
            "type": "score",
            "instructions": "Rate how relevant these logs are to the described incident (e.g., do they show the root cause?).",
            "criteria": ["irrelevant", "minor_clue", "strong_evidence", "root_cause"]
        }
    }
    
    prompt = f"Context: {incident_context}\nLogs:\n{logs_text}"
    result = router.predict(prompt, questions)
    
    # Laya returns a score float [0, len(criteria)-1]. 
    # For 4 items, score is between 0.0 and 3.0.
    # We will normalize it to a 0-10 scale.
    score_0_to_3 = result["answers"]["relevance"].get("score", 0.0)
    normalized = (score_0_to_3 / 3.0) * 10.0
    
    return round(normalized, 2)
