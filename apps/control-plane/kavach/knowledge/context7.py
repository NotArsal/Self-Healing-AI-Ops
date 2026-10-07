import json
import logging
import os
import httpx

from kavach.docs.queries import DOC_QUERIES

logger = logging.getLogger(__name__)

CACHE_FILE = ".context7_cache.json"
CONTEXT7_API_URL = os.environ.get("CONTEXT7_API_URL", "http://context7.example.com")


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
    """Run once at preflight. Resolves library IDs and pre-warms all query caches."""
    cache = _load_cache()

    resolved_ids = {}

    # 1. Resolve library IDs
    for dep in dependencies:
        cache_key = f"resolve_{dep}"
        if cache_key not in cache:
            try:
                # Real network call with 5s timeout
                response = httpx.post(
                    f"{CONTEXT7_API_URL}/resolve-library-id",
                    json={"library": dep},
                    timeout=5.0,
                )
                if response.status_code == 200:
                    cache[cache_key] = response.json().get(
                        "library_id", f"/{dep}/mocked"
                    )
                else:
                    cache[cache_key] = f"/{dep}/mocked"
            except Exception as e:
                logger.warning(f"Context7 resolution failed (non-fatal): {e}")
                cache[cache_key] = f"/{dep}/mocked"

        resolved_ids[dep] = cache[cache_key]

    # 2. Pre-warm document queries for all target fault classes
    target_faults = ["F05", "F08", "F09", "UNKNOWN"]
    for fault_class in target_faults:
        queries = DOC_QUERIES.get(fault_class, [])[:2]
        for query in queries:
            cache_key = f"{fault_class}_{query}"
            if cache_key not in cache:
                try:
                    # Pre-fetch the documentation using resolved IDs
                    response = httpx.post(
                        f"{CONTEXT7_API_URL}/query-docs",
                        json={"query": query, "libraries": list(resolved_ids.values())},
                        timeout=5.0,
                    )
                    if response.status_code == 200:
                        cache[cache_key] = response.json().get(
                            "content", f"Retrieved Docs for '{query}'"
                        )
                    else:
                        cache[cache_key] = (
                            f"Retrieved Docs for '{query}': Fallback mock data."
                        )
                except Exception as e:
                    logger.warning(f"Context7 query failed (non-fatal): {e}")
                    cache[cache_key] = (
                        f"Retrieved Docs for '{query}': Fallback mock data."
                    )

    _save_cache(cache)


def query_docs_for_incident(fault_class: str, dependencies: list[str]) -> str:
    """
    Fetch documentation evidence for specific fault classes.
    Only for F05, F08, F09, and UNKNOWN.
    Reads entirely from the cache, maintaining the Zero-Network guarantee during incidents.
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
        else:
            # Cache miss! Zero-network guarantee means we MUST NOT make a network call here.
            # We log a warning and return what we can.
            logger.warning(
                f"Context7 Cache Miss for {cache_key}. Network calls disabled during incident."
            )

    return "\n\n".join(evidence_blocks)
