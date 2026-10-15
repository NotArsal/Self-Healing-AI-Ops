from kavach.remediation.executor import execute_http


def test_execute_http_injects_trace_headers(monkeypatch) -> None:
    # No safety stub: the executor no longer consults shadow Laya before acting.
    # permit() decided in gate_node, and Laya may not gate (AGENTS.md).
    captured_headers = {}

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def build_request(self, method, url, json=None, headers=None):
            if headers:
                captured_headers.update(headers)

            # Return a dummy request object
            class DummyReq:
                pass

            return DummyReq()

        def send(self, req):
            class DummyRes:
                is_success = True
                text = "mock response"

            return DummyRes()

    monkeypatch.setattr("httpx.Client", MockClient)

    from opentelemetry import trace
    from opentelemetry.trace import NonRecordingSpan, SpanContext

    # Let's create a fake traceparent by starting a span
    span = NonRecordingSpan(SpanContext(trace_id=1, span_id=1, is_remote=False))

    with trace.use_span(span, end_on_exit=True):
        success, text = execute_http("POST", "http://mocked/api", {"payload": "test"})

    assert success is True
    assert text == "mock response"
    assert "traceparent" in captured_headers
    assert captured_headers["traceparent"].startswith(
        "00-00000000000000000000000000000001-0000000000000001"
    )
