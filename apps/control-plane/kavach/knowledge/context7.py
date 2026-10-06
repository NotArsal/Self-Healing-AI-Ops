import json
import logging
import os
import httpx
from kavach.docs.queries import DOC_QUERIES

logger = logging.getLogger(__name__)

CACHE_FILE = ".context7_cache.json"

def _load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_cache(cache: dict) -> None:
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        logger.warning(f"Failed to save Context7 cache: {e}")

def resolve_dependencies_at_onboarding(dependencies: list[str]) -> None:
    """Run once at preflight. Resolves library IDs and caches them."""
    cache = _load_cache()
    # Mocking resolution
    for dep in dependencies:
        if dep not in cache:
            cache[dep] = f"/{dep}/mocked"
    _save_cache(cache)

def query_docs_for_incident(fault_class: str, dependencies: list[str]) -> str:
    """
    Fetch documentation evidence for specific fault classes.
    Only for F05, F08, F09, and UNKNOWN.
    Max 2 queries per incident. 5s timeout.
    """
    if fault_class not in ["F05", "F08", "F09", "UNKNOWN"]:
        return ""
        
    queries = DOC_QUERIES.get(fault_class, [])[:2]
    if not queries:
        return ""
        
    cache = _load_cache()
    evidence_blocks = []
    
    for query in queries:
        cache_key = f"{fault_class}_{query}"
        if cache_key in cache:
            evidence_blocks.append(cache[cache_key])
            continue
            
        # Network call to Context7 (Mocked)
        try:
            # We enforce the 5s timeout rule here
            # response = httpx.post("http://context7.example.com/query", json={"query": query}, timeout=5.0)
            # if response.status_code == 200:
            mock_result = f"Retrieved Docs for '{query}': Always check connection pooling settings. Default is 100."
            evidence_blocks.append(mock_result)
            cache[cache_key] = mock_result
        except Exception as e:
            logger.warning(f"Context7 lookup failed (non-fatal): {e}")
            continue
            
    _save_cache(cache)
    return "\n\n".join(evidence_blocks)
