"""Model providers. One registry, one OpenAI-compatible client, one factory.

Ollama stays the default and stays the reported configuration (`PL-02`: no
cloud key may be REQUIRED for Kavach to run). The cloud providers exist
because of one measured finding: no local 3B-7B model wrote a unified diff
that applies, 0 of 15 (ADR 0011). Diagnosis is not the bottleneck; writing a
diff is, and the obvious next variable is a bigger model.

WHY ONE CLIENT FOR FOUR PROVIDERS
Groq, OpenRouter, Gemini and OpenCode Zen all speak the OpenAI chat
completions protocol: `POST {base}/chat/completions`, a bearer token, and
`response_format` for structured output. So they differ only in a base URL,
an environment variable and a default model, which makes them a TABLE rather
than four classes. Adding a provider is one row.

Ollama is the odd one out - its own `/api/chat` with a `format` field - and
it already has a working client, so it keeps it.

EVERY RESPONSE CARRIES THE PROVIDER THAT PRODUCED IT
`LlmResponse.provider` is not decoration. Every number in this project is
"model X scored Y": RCA 10 of 10, the 0 of 15 diff finding, the MTTR
figures. The moment the provider can vary between runs, a result without its
provenance is unreproducible, and the measurements are the deliverable. So
provenance travels with the response rather than being remembered by the
caller.

NO SILENT FALLBACK BETWEEN PROVIDERS
There is deliberately no "try the cloud, fall back to Ollama" path here. It
would make the model that produced a given result non-deterministic, which
is the same defect in a different coat. A caller that wants a fallback must
ask for each provider explicitly and record which one answered.

SECRETS
A key is read from the environment, sent in a header, and never logged,
never put in an exception message, and never written to a record. The error
paths below quote status codes and response bodies; `_scrub` exists because
a provider that echoes the Authorization header into an error body would
otherwise leak it into an audit log that is append-only by design.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Any

from kavach.llm.client import (
    LlmClient,
    LlmError,
    LlmResponse,
    OllamaClient,
    assert_not_proxied,
)

OLLAMA = "ollama"

# Sent on every cloud request, and it is load-bearing rather than polite.
#
# Groq and OpenCode Zen sit behind Cloudflare, which answers the default
# `Python-urllib/3.12` with HTTP 403 and `error code: 1010` - its browser
# integrity check. That reads exactly like a rejected key and sent this
# project looking at the wrong thing for a while, so the fix is recorded
# next to the cause.
#
# It names Kavach honestly. It is deliberately NOT a copied browser string:
# the problem is an unidentified client, and the fix for that is to identify
# the client, not to impersonate a different one.
USER_AGENT = (
    "Kavach/1.0 (self-healing-ai-ops; "
    "+https://github.com/NotArsal/Self-Healing-AI-Ops)"
)


@dataclass(frozen=True)
class Provider:
    """One OpenAI-compatible endpoint."""

    name: str
    base_url: str
    key_env: str
    default_model: str
    note: str = ""
    # Not every "OpenAI-compatible" layer accepts every OpenAI field.
    # Gemini's rejects `seed` outright with HTTP 400 "Unknown name seed:
    # Cannot find field", so the determinism hint is dropped for it rather
    # than dropped for everyone. Providers that honour it stay reproducible.
    supports_seed: bool = True
    # The output budget. 2048 is generous for what the schemas allow - the
    # diff is capped at 4000 characters and the rationale at 600 - but a
    # REASONING model spends hidden thinking tokens out of the same budget
    # and they do not appear in `completion_tokens`. Gemini 3.8-flash spent
    # ~3000 on this project's patch prompt and returned 33 tokens of answer
    # under a 2048 cap, sometimes cut mid-string. At 8192 it returns a whole
    # one. So the budget is per-provider rather than one number that is
    # wrong for somebody.
    max_output_tokens: int = 2048


# The table. A base URL here NEVER includes `/chat/completions`: the client
# appends it, and including it doubles the path for a 404 that looks like an
# auth problem.
PROVIDERS: dict[str, Provider] = {
    "openrouter": Provider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        key_env="KAVACH_OPENROUTER_API_KEY",
        default_model="anthropic/claude-sonnet-4.5",
        note="one key, most models; model string selects the vendor",
    ),
    "groq": Provider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        key_env="KAVACH_GROQ_API_KEY",
        default_model="llama-3.3-70b-versatile",
        note="fast inference, open-weight models only",
    ),
    "gemini": Provider(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        key_env="KAVACH_GEMINI_API_KEY",
        # 2.5-flash was retired for new users on 2026-10-18; the API
        # itself named 3.8-flash as the replacement.
        default_model="gemini-3.8-flash",
        note="Google's OpenAI-compatibility layer, not the native API",
        supports_seed=False,
        max_output_tokens=8192,
    ),
    "opencodezen": Provider(
        name="opencodezen",
        base_url="https://opencode.ai/zen/v1",
        key_env="KAVACH_OPENCODEZEN_API_KEY",
        # RE-CHECKED 2026-10-19 and KEPT. It was up for removal on the
        # suspicion it did not work; `GET /zen/v1/models` answers 200 with 85
        # models, so the row was not broken - it was incomplete. The earlier
        # expired key had stopped the list being read, and an empty
        # `default_model` then made every call fail in a way that looked like
        # a dead provider.
        default_model="deepseek-v4.1-flash-free",
        note="85 models, list is public at /zen/v1/models; the -free tier "
             "suits PL-02's no-required-cost posture",
    ),
    # --- added 2026-10-19 --------------------------------------------------
    "ollamacloud": Provider(
        name="ollamacloud",
        base_url="https://ollama.com/v1",
        key_env="KAVACH_OLLAMACLOUD_API_KEY",
        # The closest thing to the measured local configuration that is not
        # on this machine: same engine, same structured-output behaviour,
        # someone else's GPU. Distinct from the `ollama` provider, which is
        # the LOCAL server and takes no key - they share a vendor and nothing
        # else, so they are two rows.
        default_model="gemma4:31b",
        note="Ollama's hosted API; 22 cloud models, list is public at "
             "https://ollama.com/api/tags. Verified 2026-10-19: "
             "/v1/chat/completions returns an OpenAI-shaped 401 without a "
             "key, so the path reaches the auth layer",
    ),
    "nvidia": Provider(
        name="nvidia",
        base_url="https://integrate.api.nvidia.com/v1",
        key_env="KAVACH_NVIDIA_API_KEY",
        # 70B instruct rather than one of the nemotron-3 reasoning models.
        # A reasoning model spends hidden thinking tokens out of the same
        # output budget - see `max_output_tokens` - and Gemini already cost
        # this project an afternoon of truncated answers that way.
        default_model="nvidia/llama-3.1-nemotron-70b-instruct",
        note="NVIDIA NIM / build.nvidia.com; 81 models, list is public at "
             "/v1/models without a key. Keys look like nvapi-...",
    ),
}

# TokenRouter is deliberately absent. It was asked for, searched for on
# 2026-10-18, and no public API could be confirmed. Inventing a base URL
# would produce a provider that fails at the first call with a misleading
# error. It is one row away whenever its documentation turns up.


def _scrub(text: str, key: str) -> str:
    """Never let a key reach a log, a record or an exception message."""
    if key and key in text:
        text = text.replace(key, "***")
    return text


def key_for(spec: Provider) -> str:
    """The key for a provider, from settings first and the environment second.

    Settings FIRST because that is where `.env` actually lands.
    `pydantic_settings` reads `.env` into the `Settings` object, not into
    `os.environ`, so a key written to `.env` - which is exactly what a user
    is told to do, and the only gitignored place for it - is invisible to
    `os.environ.get`. Reading the environment alone would mean every key
    silently appeared absent unless it had also been exported by hand.

    The environment is still consulted, because compose and CI set variables
    that way and never write a `.env`.
    """
    field = f"{spec.name}_api_key"
    try:
        from kavach.config import get_settings

        value = str(getattr(get_settings(), field, "") or "")
        if value:
            return value
    except Exception:
        # Settings may be unconstructable in a bare context (a probe script,
        # a test). The environment is then the only source, which is fine.
        pass
    return os.environ.get(spec.key_env, "")


class OpenAiCompatClient:
    """Any provider that speaks OpenAI chat completions.

    Structured output uses `response_format: {"type": "json_schema", ...}`
    with `strict: true`, which is the closest equivalent to Ollama's
    grammar-constrained decoding. Our schemas already set
    `additionalProperties: false` and list every property in `required`,
    which strict mode requires, so they pass through unchanged.

    A provider that does not support strict json_schema fails loudly here
    rather than quietly degrading to free text. Degrading would mean the
    decoder constraint silently stopped existing, and `rca/schema.py` records
    at length what unconstrained decoding costs this project.
    """

    def __init__(
        self,
        provider: Provider,
        model: str = "",
        api_key: str = "",
        timeout_s: float = 180.0,
    ) -> None:
        assert_not_proxied(provider.base_url)
        self.provider = provider
        self.base_url = provider.base_url.rstrip("/")
        self.model = model or provider.default_model
        self._key = api_key or key_for(provider)
        self.timeout_s = timeout_s
        if not self.model:
            raise LlmError(
                f"provider {provider.name!r} has no default model, so a model "
                f"must be given explicitly (KAVACH_LLM_MODEL)"
            )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._key}",
            "User-Agent": USER_AGENT,
        }

    # --- availability -------------------------------------------------------

    def available(self) -> bool:
        """A key is present and `/models` answers.

        Checked rather than assumed because the failure it catches - a key
        that is absent, expired or for the wrong provider - otherwise surfaces
        in the middle of a measurement run as a 401 that looks like a model
        problem.
        """
        if not self._key:
            return False
        try:
            req = urllib.request.Request(
                f"{self.base_url}/models", headers=self._headers())
            with urllib.request.urlopen(req, timeout=15) as r:
                json.load(r)
            return True
        except Exception:
            return False

    # --- the one call -------------------------------------------------------

    def structured(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> LlmResponse:
        if not self._key:
            raise LlmError(
                f"no API key for {self.provider.name}: set "
                f"{self.provider.key_env} in .env. Kavach runs on Ollama "
                f"without any cloud key (PL-02); a cloud provider is opt-in"
            )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "kavach_reply",
                    "strict": True,
                    "schema": schema,
                },
            },
            "stream": False,
            # Bounded on purpose, and not only to control cost.
            #
            # Left unset, a provider assumes its model's maximum. OpenRouter
            # reserves credits against that assumption and refused with HTTP
            # 402 - "you requested up to 64000 tokens, but can only afford
            # 97" - which reads like an empty account rather than a missing
            # parameter. The per-provider value is on the table row.
            "max_tokens": self.provider.max_output_tokens,
            # Same determinism contract as the Ollama path. `seed` is added
            # below only where the provider accepts it - see `supports_seed`.
            "temperature": temperature,
            "top_p": 1.0,
        }
        if self.provider.supports_seed:
            payload["seed"] = 42
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={**self._headers(), "Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                data = json.load(r)
        except urllib.error.HTTPError as exc:
            detail = ""
            with contextlib.suppress(Exception):
                detail = exc.read().decode("utf-8", "replace")[:300]
            raise LlmError(
                f"{self.provider.name} returned HTTP {exc.code}: "
                f"{_scrub(detail, self._key)}"
            ) from exc
        except Exception as exc:
            raise LlmError(
                f"{self.provider.name} call failed: "
                f"{_scrub(str(exc), self._key)}"
            ) from exc
        elapsed = time.perf_counter() - started

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError(
                f"unexpected {self.provider.name} response shape: "
                f"{_scrub(str(data)[:300], self._key)}"
            ) from exc
        if content is None:
            raise LlmError(
                f"{self.provider.name} returned no content; the model may "
                f"have refused or hit a length limit"
            )

        usage = data.get("usage") or {}
        return LlmResponse(
            raw=str(content),
            model=str(data.get("model") or self.model),
            latency_s=elapsed,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            provider=self.provider.name,
        )


def names() -> list[str]:
    """Every provider that can be selected, Ollama included."""
    return [OLLAMA, *sorted(PROVIDERS)]


def build(
    provider: str = OLLAMA,
    model: str = "",
    ollama_base_url: str = "",
    api_key: str = "",
    base_url: str = "",
) -> LlmClient:
    """The one way to obtain a model client.

    `provider` is explicit. There is no auto-detection from which key happens
    to be set: that would make the model behind a measurement depend on the
    contents of a `.env` file nobody reads, and the whole point of carrying
    provenance is that it is never inferred.

    THE TWO URL PARAMETERS ARE SEPARATE ON PURPOSE
    `ollama_base_url` is where Ollama listens and is IGNORED by every cloud
    provider. `base_url` overrides a cloud provider's own endpoint and is
    ignored by Ollama.

    They were one parameter for about an hour, and every caller had an
    Ollama URL to hand (`settings.llm_base_url`, `--ollama`) and passed it
    positionally. So selecting OpenRouter sent the request to
    127.0.0.1:11434, Ollama replied `404 page not found`, and three
    different providers produced byte-identical errors that looked like a
    routing problem at their end. Two names cost nothing and make that
    unrepresentable.
    """
    key = provider.strip().lower() or OLLAMA
    if key == OLLAMA:
        return OllamaClient(
            base_url=ollama_base_url or "http://localhost:11434",
            model=model or "llama3.2",
        )
    spec = PROVIDERS.get(key)
    if spec is None:
        raise LlmError(
            f"unknown provider {provider!r}; available: {names()}"
        )
    if base_url:
        # `replace`, not a fresh Provider. Rebuilding it field by field
        # dropped `supports_seed` and `max_output_tokens` back to their
        # defaults, so `--base-url` against Gemini silently re-enabled the
        # `seed` it answers 400 to and cut its budget from 8192 to 2048.
        # Every field the table sets has a measured reason behind it; an
        # override of one of them must not quietly revert the others.
        spec = replace(spec, base_url=base_url)
    return OpenAiCompatClient(spec, model=model, api_key=api_key)
