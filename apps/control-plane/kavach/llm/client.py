"""Ollama client for Kavach's own reasoning. Structured output only.

Two properties this module exists to guarantee.

SCHEMA-CONSTRAINED GENERATION, NOT TEXT PARSING
Ollama's `format` field takes a JSON Schema and constrains decoding to it, so
the model cannot emit prose, a markdown fence, or a differently-shaped object.
Scraping JSON out of free text with a regex is the usual approach and it fails
in exactly the cases that matter - the model hedges, apologises, or wraps the
answer in explanation - so it is not used here. The schema is still validated
again on receipt, because a constrained decoder is a strong guarantee, not a
proof.

DIRECT TO OLLAMA, NEVER THROUGH THE FAULT-INJECTION PROXY
The target reaches Ollama via Toxiproxy so F01/F02 can break its path. Kavach
must not: if the diagnostician's own model calls went through the faulted path,
injecting a fault would blind the component trying to diagnose it (PRD §6.3).
`assert_not_proxied` makes that a checked property rather than a convention.

Temperature is 0. A diagnosis that changes between identical inputs is not a
diagnosis, and every downstream check assumes the same evidence yields the same
verdict.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class LlmError(RuntimeError):
    """The model could not be reached, or returned something unusable."""


@dataclass(frozen=True)
class LlmResponse:
    raw: str
    model: str
    latency_s: float
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def parsed(self) -> Any:
        """The decoded JSON object. Raises LlmError if it is not JSON.

        A constrained decoder should make this impossible; it is checked anyway
        because "should be impossible" is not a safety property.
        """
        try:
            return json.loads(self.raw)
        except json.JSONDecodeError as exc:
            raise LlmError(
                f"model returned text that is not JSON despite a schema "
                f"constraint: {self.raw[:200]!r}"
            ) from exc


def assert_not_proxied(base_url: str) -> None:
    """Refuse a base URL that routes through the fault-injection proxy."""
    lowered = base_url.lower()
    for marker in ("toxiproxy", ":21434", ":21435"):
        if marker in lowered:
            raise LlmError(
                f"refusing to use {base_url!r}: it routes through the "
                f"fault-injection proxy, so injecting F01/F02 would blind RCA "
                f"itself (PRD §6.3). Point KAVACH_LLM_BASE_URL at Ollama directly."
            )


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout_s: float = 120.0,
    ) -> None:
        assert_not_proxied(base_url)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    def available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=10) as r:
                json.load(r)
            return True
        except Exception:
            return False

    def structured(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> LlmResponse:
        """One schema-constrained completion.

        `schema` is a JSON Schema. Ollama constrains decoding to it, so the
        reply is a JSON object of that shape or the call fails.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "stream": False,
            "options": {
                # Deterministic: identical evidence must yield an identical
                # diagnosis, or none of the downstream checks mean anything.
                "temperature": temperature,
                "top_p": 1.0,
                "seed": 42,
            },
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                data = json.load(r)
        except urllib.error.HTTPError as exc:
            raise LlmError(f"Ollama returned HTTP {exc.code}") from exc
        except Exception as exc:
            raise LlmError(f"Ollama call failed: {exc}") from exc
        elapsed = time.perf_counter() - started

        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LlmError(f"unexpected Ollama response shape: {data!r}") from exc

        return LlmResponse(
            raw=content,
            model=str(data.get("model", self.model)),
            latency_s=elapsed,
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            completion_tokens=int(data.get("eval_count") or 0),
        )
