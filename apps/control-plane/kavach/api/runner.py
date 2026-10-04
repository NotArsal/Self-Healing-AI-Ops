"""Drives the existing loop for the console, and remembers what it did.

This module adds no healing logic. It calls `loop.run_once` exactly as the
harnesses do, hands it an `on_event` sink so the console can watch, and keeps
the returned incidents in memory so the history table has rows.

THREE THINGS IT ENFORCES

1. **Single flight.** One loop at a time, process-wide. Two concurrent runs
   would both read a pre-state and both write a config, and the second
   inverse would point at the first run's faulty value. The real writer lock
   is P6 (`ARCHITECTURE.md` §6.0); this is the narrow version that keeps the
   console from being the thing that breaks the guarantee.

2. **Operator-triggered only.** There is no timer. A background tick that
   healed unattended would need the mode gate, and `permit()` does not exist
   until P6 - see the amendment on `docs/decisions/0006`. A run happens
   because somebody asked for one.

3. **A real baseline or nothing.** The rollback target comes from the newest
   baseline capture on disk, the same artifact `make onboard` writes. With no
   capture, the run is refused rather than run against a guessed threshold -
   the same stance `ConfigRollback.prepare()` takes.

In-memory storage is what P4 was scoped to: `Incident` is a dataclass and
there is no database yet. Restarting the control plane loses history, which is
honest and is why the harness still writes JSON artifacts.
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from kavach import loop
from kavach.api.events import bus
from kavach.config import Settings
from kavach.detection import retrieval_collapse as rc
from kavach.llm.client import OllamaClient
from kavach.onboarding.baseline import _promql
from kavach.rca import evidence as ev
from kavach.rca.engine import diagnose
from kavach.target import TargetClient, TargetEndpoints
from kavach.verification import fast

logger = structlog.get_logger(__name__)

# Enough for a demo and a rehearsal; this is not a knowledge base (that is P7).
HISTORY_MAX = 50


class LoopBusyError(RuntimeError):
    """A run is already in flight."""


class NoBaselineError(RuntimeError):
    """No captured known-good value, so there is nothing to roll back to."""


def newest_baseline(kavach_root: Path, project: str) -> tuple[float | None, str]:
    """The rerank_threshold from the most recent capture, and its filename."""
    d = kavach_root / "harness" / "baselines"
    if not d.is_dir():
        return None, ""
    files = sorted(d.glob(f"baseline-{project}-*.json"))
    for path in reversed(files):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        value = doc.get("rerank_threshold")
        if isinstance(value, int | float):
            return float(value), path.name
    return None, ""


class LoopRunner:
    """Owns the incident history and the one-at-a-time run slot."""

    def __init__(self, settings: Settings, kavach_root: Path) -> None:
        self.settings = settings
        self.root = kavach_root
        self._incidents: dict[str, loop.Incident] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._running: str = ""

    # --- target wiring ------------------------------------------------------

    def client(self) -> TargetClient:
        s = self.settings
        return TargetClient(
            TargetEndpoints(
                health=s.target_health_url,
                chat=s.target_chat_url,
                config=s.target_config_url,
                admin_token=s.target_admin_token,
            )
        )

    def fast_set_path(self) -> Path:
        return self.root / "apps" / "control-plane" / "kavach" / "verification" / "fast_set.yaml"

    def baseline(self) -> tuple[float | None, str]:
        return newest_baseline(self.root, self.settings.target_project)

    # --- history ------------------------------------------------------------

    @property
    def running_incident_id(self) -> str:
        return self._running

    @property
    def busy(self) -> bool:
        return bool(self._running)

    def incidents(self) -> list[loop.Incident]:
        """Newest first."""
        return [self._incidents[i] for i in reversed(self._order)]

    def incident(self, incident_id: str) -> loop.Incident | None:
        return self._incidents.get(incident_id)

    def _remember(self, inc: loop.Incident) -> None:
        if inc.incident_id not in self._incidents:
            self._order.append(inc.incident_id)
        self._incidents[inc.incident_id] = inc
        while len(self._order) > HISTORY_MAX:
            self._incidents.pop(self._order.pop(0), None)

    # --- running ------------------------------------------------------------

    def _rca_stage(self, client: TargetClient, publish: Any) -> loop.RcaStage:
        """The same stage `harness/rca_f06_live.py` builds, plus two events.

        `evidence collected` and `diagnosis returned` are only observable from
        inside this wrapper, because the loop sees RCA as one opaque call.
        """
        s = self.settings
        llm = OllamaClient(s.llm_base_url, s.llm_model)
        services = set(s.target_services())
        baseline_value, _ = self.baseline()

        def stage(
            fast_result: fast.FastVerificationResult,
            detection: rc.Detection,
            baseline: float | None,
        ) -> Any:
            frame = ev.collect(
                client, s.prometheus_url, _promql, fast_result,
                baseline_rerank_threshold=baseline if baseline is not None else baseline_value,
            )
            publish("evidence", "ok",
                    f"evidence collected: {len(frame.items)} citable items"
                    + (f"; {len(frame.problems)} collection problem(s)"
                       if frame.problems else ""))
            return diagnose(
                frame, detection, s.confidence_threshold, llm=llm,
                declared_services=services,
            )

        return stage

    async def start(self, use_rca: bool = True) -> loop.Incident:
        """Begin a run. Returns as soon as the incident exists, not when it ends."""
        with self._lock:
            if self._running:
                raise LoopBusyError(
                    f"a loop run is already in flight ({self._running}); "
                    f"one writer at a time"
                )
            baseline_value, source = self.baseline()
            if baseline_value is None:
                raise NoBaselineError(
                    "no baseline capture under harness/baselines/. Run "
                    "`make onboard` against a healthy target first: a rollback "
                    "with no recorded known-good value would be a guess."
                )
            incident_id = f"INC-{datetime.now(UTC).strftime('%H%M%S')}"
            self._running = incident_id

        event_loop = asyncio.get_running_loop()

        def publish(stage: str, status: str, message: str) -> None:
            bus.publish_threadsafe(
                event_loop, stage, status, message, incident_id=incident_id
            )

        publish("run", "started",
                f"operator started a loop run; baseline rerank_threshold "
                f"{baseline_value} from {source}; "
                f"{'LLM RCA enabled' if use_rca else 'deterministic only'}")

        client = self.client()
        rca_stage = self._rca_stage(client, publish) if use_rca else None

        inc = loop.Incident(
            incident_id=incident_id,
            project=self.settings.target_project,
            detected_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        self._remember(inc)

        def work() -> None:
            try:
                result = loop.run_once(
                    client,
                    self.settings.prometheus_url,
                    self.fast_set_path(),
                    _promql,
                    baseline_value,
                    project=self.settings.target_project,
                    incident_id=incident_id,
                    rca=rca_stage,
                    on_event=publish,
                )
                self._remember(result)
                ok = result.status is loop.IncidentStatus.RESOLVED
                quiet = result.status is loop.IncidentStatus.NO_FAULT
                publish(
                    "resolve",
                    "ok" if ok else ("info" if quiet else "failed"),
                    result.outcome or result.escalation_reason or str(result.status),
                )
            except Exception as exc:
                # Total on purpose: this runs in a worker thread, where an
                # escaping exception would vanish and leave the slot held.
                logger.exception("loop run failed", incident_id=incident_id)
                inc.status = loop.IncidentStatus.ESCALATED
                inc.escalation_reason = f"{type(exc).__name__}: {exc}"
                inc.outcome = "escalated; the run did not complete"
                self._remember(inc)
                publish("resolve", "failed", inc.escalation_reason)
            finally:
                with self._lock:
                    self._running = ""

        threading.Thread(
            target=work, name=f"kavach-loop-{incident_id}", daemon=True
        ).start()
        return inc
