"""F01 primary LLM endpoint outage.

Disables the `ollama-primary` Toxiproxy listener, so the target's configured
`llm_base_url` (`http://toxiproxy:21434`) stops accepting connections. The
target then fails to reach any model: `/healthz` reports its `ollama`
dependency down, and chat requests error rather than returning a wrong answer.

WHY THIS IS A DIFFERENT SHAPE OF FAULT FROM F06, AND WHY THAT MATTERS
`F06` is the silent-200 case: the system is up and wrong, HTTP status is
useless, and detection has to come from application-level grounding metrics.
`F01` is the opposite and is the control: the dependency is visibly down, the
health probe says so, and detection is cheap. Having both in the catalogue is
what stops the research claim resting on one fault shape.

WHY DISABLE THE LISTENER RATHER THAN ADD A TOXIC
Toxiproxy can inject latency, bandwidth limits and partial failures, and `F02`
(latency degradation) is exactly that. An *outage* is the listener being gone,
which `enabled: false` models exactly: connections are refused immediately
rather than hanging. A timeout-shaped toxic would be `F02` wearing `F01`'s
name, and the two would stop being distinguishable - which is the whole point
of having a catalogue.

THE BACKUP LISTENER IS THE REPAIR TARGET, AND IS NEVER FAULTED
`toxiproxy.json` declares two listeners forwarding to the SAME host Ollama:
`:21434` primary, fault-injectable, and `:21435` backup, left clean. The repair
is therefore `switch_llm_endpoint` to the backup, not re-enabling the proxy -
re-enabling would be the injector undoing itself, which proves nothing. This
is endpoint-level failover, NOT independent providers: there is one Ollama on
this machine, and `toxiproxy/README.md` says so.

`inject()` asserts the backup is up BEFORE breaking the primary, because a
failover test against a dead failover target measures nothing.

MEASURED 2026-10-16, AND IT SETTLES THE F01-vs-F02 QUESTION
Unlike `F06`'s `BAD_THRESHOLD` there is no constant to sweep here - disabling a
listener is binary - but the timing was measured on a live target and it is the
reason this shape is correct:

    target surfaced the outage on /healthz   0.034 s
    target recovered after revert            0.075 s
    /healthz status under fault              503 (not 200)
    detail                                   "HTTPConnectionPool(host=
                                             'toxiproxy', port=21434): Max
                                             retries exceeded"

Effectively instant, because a disabled listener REFUSES the connection
instead of hanging. `LLM_TIMEOUT_SECONDS=30` is therefore never reached, which
is exactly the separation wanted: `F01` is refusal in milliseconds, `F02` is a
timeout at the 30s ceiling, and the two cannot be confused in the evidence. A
latency toxic here would have collapsed them into one fault.

The 503 is also the whole contrast with `F06`: HTTP status carries the fault
outright, so detection is cheap, where `F06` returns 200 and only the answers
are wrong. The catalogue needs both shapes or the research claim rests on one.

Still unmeasured: the 20-cycle stability run, and how the chat path behaves
mid-request when the listener drops under it.

NOT TOUCHED: the corpus, the embedding model, the prompts, the backup
listener, and every target setting other than what the repair itself writes.
The injector asserts the first of those.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from harness.faults.base import Fault, InjectionRecord

# The admin API the target's compose publishes for exactly this purpose
# ("admin API, driven by the fault injector").
TOXIPROXY_ADMIN = "http://127.0.0.1:8474"

PRIMARY = "ollama-primary"
BACKUP = "ollama-backup"

# Documented for reference. revert() replays the captured pre-state, never a
# constant, so these are not fallbacks.
EXPECTED_PRIMARY_LISTEN = "0.0.0.0:21434"
EXPECTED_BACKUP_LISTEN = "0.0.0.0:21435"


class ToxiproxyError(RuntimeError):
    """The admin API could not be reached or refused the change."""


def _call(path: str, method: str = "GET", body: dict[str, Any] | None = None,
          timeout: float = 10.0) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        TOXIPROXY_ADMIN + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raise ToxiproxyError(
            f"{method} {path} -> HTTP {exc.code} {exc.read().decode()[:200]}"
        ) from exc
    except OSError as exc:
        raise ToxiproxyError(
            f"{method} {path} -> {exc}. Is the target stack up? The admin API "
            f"is published on 8474 by the target's compose."
        ) from exc


class F01EndpointOutage(Fault):
    fault_class = "F01"
    fault_name = "endpoint_outage"
    service = "backend"

    def __init__(
        self,
        corpus_probe: Callable[[], dict[str, Any]] | None = None,
        proxy: str = PRIMARY,
        backup: str = BACKUP,
    ) -> None:
        super().__init__()
        self.proxy = proxy
        self.backup = backup
        # Injected so the injector can assert corpus immutability without
        # reaching into the database itself, exactly as F06 does.
        self._corpus_probe = corpus_probe or (lambda: {})

    # --- state --------------------------------------------------------------

    def _proxy(self, name: str) -> dict[str, Any]:
        record = _call(f"/proxies/{name}")
        if not isinstance(record, dict):
            raise ToxiproxyError(f"proxy {name!r} not found on the admin API")
        return record

    def is_active(self) -> bool:
        return self._proxy(self.proxy).get("enabled") is False

    def backup_is_up(self) -> bool:
        return self._proxy(self.backup).get("enabled") is True

    # --- inject / revert ----------------------------------------------------

    def inject(self) -> InjectionRecord:
        before = self._proxy(self.proxy)
        if before.get("enabled") is not True:
            raise RuntimeError(
                f"{self.proxy!r} is already disabled, so there is no healthy "
                f"pre-state to capture or to restore. Revert a previous run first."
            )
        # A failover fault whose failover target is down measures nothing.
        if not self.backup_is_up():
            raise RuntimeError(
                f"{self.backup!r} is not enabled. The repair for this fault is "
                f"a switch TO it, so injecting now would test a failover into a "
                f"hole rather than a repair."
            )

        self.record.pre_state = {
            "proxy": dict(before),
            "backup": dict(self._proxy(self.backup)),
        }
        self.record.corpus_before = self._corpus_probe()

        _call(f"/proxies/{self.proxy}", "POST", {"enabled": False})
        self.record.applied = {"proxy": self.proxy, "enabled": False}
        self._stamp_injected()
        return self.record

    def revert(self) -> InjectionRecord:
        prior = self.record.pre_state.get("proxy")
        if not prior:
            # Nothing captured means nothing was injected. Enabling a proxy we
            # never read would be writing a guessed value.
            return self.record
        _call(f"/proxies/{self.proxy}", "POST",
              {"enabled": prior.get("enabled")})
        self.record.corpus_after = self._corpus_probe()
        self._stamp_reverted()
        return self.record

    # --- assertions the injector owns ---------------------------------------

    def assert_scope_respected(self) -> tuple[bool, str]:
        """Only the primary listener may differ from the pre-state."""
        before = self.record.pre_state.get("backup")
        if not before:
            return False, "no pre-state captured"
        live = self._proxy(self.backup)
        drift = {k: {"before": before.get(k), "live": live.get(k)}
                 for k in before if live.get(k) != before.get(k)}
        if drift:
            return False, f"the backup listener changed: {drift}"
        return True, f"{self.backup!r} untouched and still enabled"

    def assert_corpus_unchanged(self) -> tuple[bool, str]:
        after = self._corpus_probe()
        before = self.record.corpus_before
        if not before:
            return False, "no corpus fingerprint captured before injection"
        if before != after:
            return False, f"CORPUS MUTATED: {before} -> {after}"
        return True, f"corpus unchanged {after}"

    def restored_exactly(self) -> tuple[bool, str]:
        """The live listener state equals the captured pre-state, exactly."""
        want = self.record.pre_state.get("proxy", {}).get("enabled")
        if want is None:
            return False, "no pre-state captured"
        live = self._proxy(self.proxy).get("enabled")
        if live != want:
            return False, f"not restored: wanted enabled={want}, live {live}"
        return True, f"restored to the captured value enabled={want}"
