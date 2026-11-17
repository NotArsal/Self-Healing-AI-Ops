"""The target's log in the console, without its users' words (ADR 0031)."""

from __future__ import annotations

import pytest

from kavach.executor.adapters import docker as docker_adapter
from kavach.rca import evidence

# Shapes copied from the live rag_backend log on 2026-11-17.
RERANK = "2026-11-17 13:51:03,200 [INFO] rag: Reranked 24 chunks; kept 2 chunks"
RAW = "\n".join([
    "2026-11-17 13:51:02,100 [INFO] main: Received chat question: 'What is my diagnosis?'",
    "Generated Queries for expansion: ['What is my diagnosis?', 'diagnosis meaning']",
    RERANK,
    'INFO:     172.18.0.1:50066 - "GET /metrics HTTP/1.1" 200 OK',
    'INFO:     127.0.0.1:56510 - "GET /healthz HTTP/1.1" 200 OK',
    'INFO:     172.18.0.5:41000 - "GET /v1/admin/config HTTP/1.1" 200 OK',
    "\rBatches: 100%|\x1b[A 1/1 [00:10<00:00]",
    "",
    "2026-11-17 13:51:05,300 [ERROR] rag: Cannot connect to LLM endpoint",
    'INFO:     172.18.0.1:50070 - "POST /v1/chat HTTP/1.1" 200 OK',
])


@pytest.fixture
def lines(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setattr(docker_adapter, "container_logs",
                        lambda container, tail=60: RAW)
    return evidence.target_log_lines()


def test_a_users_question_never_reaches_the_console(lines: list[str]) -> None:
    assert not any("diagnosis" in line for line in lines)


def test_noise_is_dropped_and_the_rest_kept_newest_first(lines: list[str]) -> None:
    assert lines == [
        'INFO:     172.18.0.1:50070 - "POST /v1/chat HTTP/1.1" 200 OK',
        "2026-11-17 13:51:05,300 [ERROR] rag: Cannot connect to LLM endpoint",
        RERANK,
    ]


def test_no_docker_means_an_empty_view_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_adapter, "container_logs",
                        lambda container, tail=60: "")
    assert evidence.target_log_lines() == []
