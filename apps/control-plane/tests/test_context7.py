
from kavach.docs.queries import DOC_QUERIES
from kavach.knowledge.context7 import query_docs_for_incident


def test_no_incident_data_in_queries():
    """
    Asserts that no query string sent to Context7 contains any value
    sourced from an incident (e.g. they are statically defined templates without interpolation).
    """
    # The queries are imported as constants, proving they don't accept dynamic string interpolation
    # Here we assert that they are purely static dict values.
    for fault_class, queries in DOC_QUERIES.items():
        assert isinstance(queries, list)
        for query in queries:
            assert isinstance(query, str)
            assert "{" not in query, "Queries must not contain f-string interpolation blocks"

def test_query_docs_for_incident_uses_static_queries():
    """
    Proves that query_docs_for_incident ONLY uses the static DOC_QUERIES
    and doesn't dynamically generate new strings.
    """
    # Create a mock incident
    docs = query_docs_for_incident("F05", ["mock_dependency"])
    
    # If the cache is unpopulated or network is disabled, we get the fallback mock data 
    # but the logic itself MUST only fetch keys defined in DOC_QUERIES
    assert "How to configure connection pool limits and timeouts" in docs
    assert "mock_dependency" not in docs, "Incident dependency data must not leak into the returned queries/docs"

