"""/v1/system never hangs on the model provider (2026-11-13).

With the API container's outbound network down, `available()` hung past 30s
and the console's health panel froze with it. Zero network: the provider is a
stand-in that answers, raises, or never returns.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from kavach.api import routes
from kavach.api.routes import ProviderCheck
from kavach.api.runner import LoopRunner
from kavach.config import Settings
from kavach.llm import providers
from kavach.target import TargetError


class Provider:
    """`available()` that answers `ok`, after `release` is set if one is given."""

    def __init__(self, ok: bool = True, release: threading.Event | None = None) -> None:
        self.ok = ok
        self.release = release
        self.calls = 0

    def available(self) -> bool:
        self.calls += 1
        if self.release is not None:
            self.release.wait(5)
        return self.ok


def test_a_hung_provider_costs_one_short_wait_and_one_thread() -> None:
    hung = threading.Event()
    provider = Provider(release=hung)
    check = ProviderCheck(wait_s=0.1)

    t0 = time.monotonic()
    assert check.get(provider.available) is None   # no answer yet
    assert check.get(provider.available) is None
    elapsed = time.monotonic() - t0

    assert elapsed < 1.0, "the caller waited on the provider"
    assert provider.calls == 1, "a second check started while one was running"
    hung.set()


def test_an_answer_is_reused_until_it_goes_stale() -> None:
    provider = Provider(ok=True)
    check = ProviderCheck(ttl_s=60)

    assert check.get(provider.available) is True
    assert check.get(provider.available) is True
    assert provider.calls == 1


def test_a_stale_answer_comes_back_at_once_while_a_fresh_one_is_fetched() -> None:
    provider = Provider(ok=True)
    # wait_s far above the 0.5s bound below, so a call that waited on the
    # refresh instead of returning the old answer would be caught.
    check = ProviderCheck(ttl_s=0, wait_s=2.0)
    assert check.get(provider.available) is True

    slow = threading.Event()
    provider.release, provider.ok = slow, False
    t0 = time.monotonic()
    assert check.get(provider.available) is True   # the last known answer
    assert time.monotonic() - t0 < 0.5
    slow.set()
    time.sleep(0.1)
    assert check.get(provider.available) is False  # the fresh one landed


def test_a_check_that_raises_reads_as_unreachable() -> None:
    def broken() -> bool:
        raise OSError("connection reset")

    assert ProviderCheck().get(broken) is False


@pytest.mark.asyncio
async def test_the_system_route_answers_while_the_provider_hangs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    hung = threading.Event()
    monkeypatch.setattr(routes, "_provider_check", ProviderCheck(wait_s=0.2))
    monkeypatch.setattr(providers, "build", lambda *_a, **_k: Provider(release=hung))
    monkeypatch.setattr(routes, "_prometheus_ok", lambda _url: (False, "down"))

    def unreachable() -> Any:
        raise TargetError("target down")

    runner = LoopRunner(Settings(kavach_root=str(tmp_path)))
    monkeypatch.setattr(runner, "client",
                        lambda: SimpleNamespace(health=unreachable, settings=unreachable))

    t0 = time.monotonic()
    out = await routes.system(Settings(kavach_root=str(tmp_path)), runner)
    elapsed = time.monotonic() - t0
    hung.set()

    row = next(d for d in out.dependencies if d.name.startswith("Ollama, Kavach"))
    assert elapsed < 2.0, f"/v1/system took {elapsed:.1f}s with a hung provider"
    assert row.ok is False
    assert row.detail == "no answer yet; still checking"
