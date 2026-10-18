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
from kavach.audit.log import AuditLog
from kavach.config import Mode, Settings
from kavach.db.store import IncidentStore
from kavach.detection import base as det
from kavach.executor import catalogue  # noqa: F401 - registers the catalogue
from kavach.executor.base import registry
from kavach.llm.client import OllamaClient
from kavach.onboarding.baseline import _promql
from kavach.onboarding.manifest import Manifest, load
from kavach.rca import evidence as ev
from kavach.rca.engine import diagnose
from kavach.safety.engine import ProjectPolicy, SafetyEngine
from kavach.target import TargetClient, TargetEndpoints
from kavach.verification import fast

logger = structlog.get_logger(__name__)

# Enough for a demo and a rehearsal; this is not a knowledge base (that is P7).
HISTORY_MAX = 50


class LoopBusyError(RuntimeError):
    """A run is already in flight."""


class NoBaselineError(RuntimeError):
    """No captured known-good value, so there is nothing to roll back to."""


class NotAwaitingError(RuntimeError):
    """The incident is not waiting for a human."""


def policy_from_manifest(m: Manifest, mode_override: Mode | None = None) -> ProjectPolicy:
    """The manifest IS the safety posture. `permit()` reads nothing else.

    A mode set from the console overrides the file for this process, because an
    operator flipping to AUTONOMOUS on stage should not require a file edit and
    a restart. The manifest stays the durable default; the override is explicit
    and visible in every decision record.
    """
    return ProjectPolicy(
        name=m.project.name,
        compose_project=m.project.compose_project,
        services=frozenset(m.services),
        allowed_actions=frozenset(m.allowed_actions),
        denied_mutations=frozenset(m.denied_mutations),
        mode=mode_override or m.mode,
        confidence_threshold=m.confidence_threshold,
    )


def newest_baseline_doc(baselines: Path, project: str) -> tuple[dict[str, Any], str]:
    """The most recent usable capture, whole, and its filename.

    "Usable" means it records a `rerank_threshold`, which is the one field the
    F06 rollback cannot be built without. The whole document is returned
    because F08 needs its `settings` snapshot, and reading the file twice to
    get two fields out of it would let the two reads disagree.
    """
    if not baselines.is_dir():
        return {}, ""
    # Newest first: the filenames carry a sortable UTC timestamp.
    for path in sorted(baselines.glob(f"baseline-{project}-*.json"), reverse=True):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(doc, dict) and isinstance(
            doc.get("rerank_threshold"), int | float
        ):
            return doc, path.name
    return {}, ""


def newest_baseline(baselines: Path, project: str) -> tuple[float | None, str]:
    """The rerank_threshold from the most recent capture, and its filename."""
    doc, name = newest_baseline_doc(baselines, project)
    value = doc.get("rerank_threshold")
    if isinstance(value, int | float):
        return float(value), name
    return None, ""


class LoopRunner:
    """Owns the incident history and the one-at-a-time run slot."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._incidents: dict[str, loop.Incident] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._running: str = ""

        self.safety = SafetyEngine(registry)
        self.audit = AuditLog(settings.root() / "harness" / "audit" / "kavach.jsonl")
        # NOT connected here. A constructor that opens a socket makes every
        # test that builds a runner wait on a database, which is how this
        # hung the suite the first time. `init_store()` is called from the
        # app's startup, where connecting is the point.
        self.store = IncidentStore(settings.database_url)

        # An operator's mode change for the life of this process. None means
        # "whatever the manifest says", which is the durable answer.
        self._mode_override: Mode | None = None

        # Incidents parked at the gate, with the evidence a human needs to
        # approve them. Kept in memory because the prepared action cannot be
        # pickled; the incident itself is persisted, so a restart loses the
        # pending approval and the operator re-runs. That is the honest
        # behaviour until the action's parameters are persisted too.
        self._awaiting: dict[str, dict[str, Any]] = {}

    def init_store(self) -> bool:
        """Connect and create tables. Safe to call twice; never raises."""
        if self.store.available():
            return True
        connected = self.store.init()
        self.audit.append(
            "store_init",
            available=connected,
            detail=self.store.unavailable_reason or "connected",
        )
        return connected

    # --- policy -------------------------------------------------------------

    def manifest(self) -> Manifest:
        return load(Path(self.settings.target_path) / "kavach.yaml")

    def policy(self) -> ProjectPolicy:
        return policy_from_manifest(self.manifest(), self._mode_override)

    def repair_values(self) -> dict[str, Any]:
        """The one declared value each repair aims at, read from the manifest.

        `rollback_config` aims at the captured baseline on disk;
        `switch_llm_endpoint` aims at the backup endpoint the workload declares.
        Both are workload configuration, which is why neither is a constant in
        the executor: a hardcoded failover URL would be a control-plane module
        knowing a workload's network topology.
        """
        baseline_value, _ = self.baseline()
        baseline_doc = self.baseline_doc()
        values: dict[str, Any] = {"rollback_config": baseline_value}
        llm = self.manifest().llm
        backup = llm.paths.backup if llm and llm.paths else None
        # Absent rather than None: the builder's own refusal message is clearer
        # than a None arriving as if it were a declared value.
        if backup:
            values["switch_llm_endpoint"] = backup

        # `rollback_prompt` aims at the prompt text the baseline captured, in
        # the directory the manifest declares. Both halves are required and
        # neither is defaulted: without the text there is nothing to restore,
        # and without the declared directory there is nowhere to write.
        #
        # This is the channel rather than the detector's `repair_target`
        # because `loop.py` reserves that for a value only detection can know.
        # Prompt text is not that - it is on disk, here, before detection runs.
        declared = self.manifest().versioned_paths.get("prompts")
        contents = baseline_doc.get("prompt_contents") or {}
        if declared and contents:
            values["rollback_prompt"] = {
                "dir": str((Path(self.settings.target_path) / declared).resolve()),
                "files": dict(contents),
            }
        return values

    @property
    def mode(self) -> Mode:
        return self.policy().mode

    def set_mode(self, mode: Mode) -> ProjectPolicy:
        """Change the operating mode for this process.

        Audited, because moving a project to AUTONOMOUS is the single most
        consequential configuration act available and an unrecorded one is
        indistinguishable from a compromise.
        """
        previous = self.mode
        self._mode_override = mode
        self.audit.append("mode_change", actor="operator",
                          previous=str(previous), mode=str(mode))
        return self.policy()

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
        """The 3-case set, resolved the same way preflight resolves it.

        `resolve_set` tries `<root>/<declared>` then
        `<root>/apps/control-plane/<declared>`, so one call covers both the
        host checkout and the image, where the package sits at `/app/kavach`.
        """
        declared = "kavach/verification/fast_set.yaml"
        found = fast.resolve_set(declared, self.settings.root())
        if found is None:
            raise FileNotFoundError(
                f"fast verification set {declared!r} not found under "
                f"{self.settings.root()}; set KAVACH_ROOT to the directory "
                f"holding Kavach's own files"
            )
        return found

    def baseline(self) -> tuple[float | None, str]:
        return newest_baseline(
            self.settings.baselines_dir(), self.settings.target_project
        )

    def baseline_doc(self) -> dict[str, Any]:
        """The whole capture, for the detectors that compare against it."""
        doc, _ = newest_baseline_doc(
            self.settings.baselines_dir(), self.settings.target_project
        )
        return doc

    # --- history ------------------------------------------------------------

    @property
    def running_incident_id(self) -> str:
        return self._running

    @property
    def busy(self) -> bool:
        return bool(self._running)

    def incidents(self) -> list[loop.Incident]:
        """Newest first, from memory."""
        return [self._incidents[i] for i in reversed(self._order)]

    def persisted(self, limit: int = HISTORY_MAX) -> list[dict[str, Any]]:
        """Newest first, from the database. Survives a restart."""
        return self.store.recent(limit)

    def fleet_metrics(self) -> dict[str, Any]:
        return self.store.fleet_metrics()

    def awaiting(self) -> list[str]:
        return sorted(self._awaiting)

    def parked_used_rca(self, incident_id: str) -> bool:
        """How the parked plan was derived, so the API can report it honestly."""
        return bool(self._awaiting.get(incident_id, {}).get("use_rca", True))

    def incident(self, incident_id: str) -> loop.Incident | None:
        return self._incidents.get(incident_id)

    def _remember(self, inc: loop.Incident) -> None:
        if inc.incident_id not in self._incidents:
            self._order.append(inc.incident_id)
        self._incidents[inc.incident_id] = inc
        while len(self._order) > HISTORY_MAX:
            self._incidents.pop(self._order.pop(0), None)
        # Best-effort. An unreachable database must never stop a heal.
        self.store.save(inc.to_dict())

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
        baseline_doc = self.baseline_doc()

        def stage(
            fast_result: fast.FastVerificationResult,
            detection: det.Detection,
            baseline: float | None,
        ) -> Any:
            frame = ev.collect(
                client, s.prometheus_url, _promql, fast_result,
                baseline_rerank_threshold=baseline if baseline is not None else baseline_value,
                # The whole captured snapshot, so every config line in the
                # frame carries its own known-good. Without it `F08` is not
                # diagnosable from the evidence at all.
                baseline_settings=dict(baseline_doc.get("settings") or {}),
                baseline_config_hash=str(baseline_doc.get("config_hash") or ""),
                baseline_prompt_files=dict(
                    (baseline_doc.get("prompt_version") or {}).get("files") or {}
                ),
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

    async def start(
        self, use_rca: bool = True, approved_from: str = ""
    ) -> loop.Incident:
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

        # Resolved before the first event, so a manifest that will not parse is
        # reported to the caller rather than surfacing inside a worker thread.
        try:
            policy = self.policy()
        except Exception as exc:
            # A missing safety policy is the same class of refusal as a missing
            # baseline: there is nothing safe to run under.
            raise NoBaselineError(
                f"the manifest could not be read, so there is no safety policy "
                f"to run under: {exc}"
            ) from exc

        publish("run", "started",
                (f"operator APPROVED {approved_from}; re-detecting and "
                 f"re-preparing against the target as it is now. "
                 if approved_from else "operator started a loop run ")
                + f"mode {policy.mode}; baseline {baseline_value} from {source}; "
                + ("LLM RCA enabled" if use_rca else "deterministic only"))

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
                    safety=self.safety,
                    policy=policy,
                    audit=self.audit,
                    approved_from=approved_from,
                    repair_values=self.repair_values(),
                    baseline=self.baseline_doc(),
                )
                self._remember(result)
                if result.decision:
                    self.store.save_decision(incident_id, result.decision)
                if result.status is loop.IncidentStatus.AWAITING:
                    # Park it. The human now has the plan, the risk tier, the
                    # pre-state and the inverse, which is everything the
                    # approval dialog needs (DESIGN_SYSTEM §7.7).
                    self._awaiting[incident_id] = {
                        "baseline_value": baseline_value,
                        "policy": policy,
                        # How this plan was DERIVED, so approving it re-derives
                        # it the same way. See `approve()`.
                        "use_rca": use_rca,
                        "at": datetime.now(UTC).isoformat(timespec="seconds"),
                    }
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

    # --- approval -----------------------------------------------------------

    async def approve(self, incident_id: str) -> loop.Incident:
        """A human authorised the parked plan. Re-run it as AUTONOMOUS.

        Re-running rather than resuming a stored plan is deliberate. The world
        may have moved since the operator looked: the fault may have cleared,
        the pre-state may be stale, another writer may have touched the target.
        Re-detecting and re-preparing means the action that executes is built
        against the target as it is NOW, and the pre-state witness it records
        is the real one. A resumed plan would restore a value that was true
        when the dialog opened.

        What the approval authorises is therefore the DECISION, not a frozen
        payload - which is also why the re-run still passes `permit()`: every
        other rule, including the deny-list and the breaker, is evaluated
        again.
        """
        with self._lock:
            if incident_id not in self._awaiting:
                raise NotAwaitingError(
                    f"{incident_id} is not awaiting approval; "
                    f"waiting: {sorted(self._awaiting) or 'none'}"
                )
            if self._running:
                raise LoopBusyError(
                    f"a loop run is already in flight ({self._running})"
                )
            parked = self._awaiting.pop(incident_id)

        self.audit.append("approved", incident_id=incident_id, actor="operator",
                          note="re-detected and re-prepared; the decision was "
                               "approved, not a frozen payload")
        # The approval travels as evidence on the request, NOT as a mode
        # override. Flipping the project to AUTONOMOUS for the duration was the
        # first implementation and it did not work: AUTONOMOUS routes a MEDIUM
        # action to the sandbox, which does not exist until P7, so the approved
        # re-run parked at AWAITING_APPROVAL a second time and the operator's
        # yes healed nothing. The mode on the project stays exactly as it is.
        # Re-derive the plan THE WAY IT WAS DERIVED, not always with RCA on.
        # Forcing RCA here discarded an operator's approval in a live F01 run:
        # the parked plan came from deterministic detection, the approved
        # re-run went through the LLM, the LLM diagnosed a different fault
        # class, the validator correctly rejected the disagreement, and the
        # incident escalated. The human had approved a sound plan and the
        # system answered by doing nothing - because approval silently changed
        # the pipeline. What a human approves is the decision, and the decision
        # has to be reached the same way twice.
        return await self.start(
            use_rca=bool(parked.get("use_rca", True)),
            approved_from=incident_id,
        )

    def reject(self, incident_id: str, reason: str) -> None:
        """A human refused the plan. The reason is required, and recorded.

        Required because a rejection without one teaches nobody anything, and
        the knowledge base (P7) is built from exactly these.
        """
        with self._lock:
            if incident_id not in self._awaiting:
                raise NotAwaitingError(f"{incident_id} is not awaiting approval")
            self._awaiting.pop(incident_id)
        if not reason.strip():
            raise ValueError("a rejection needs a reason")
        self.audit.append("rejected", incident_id=incident_id,
                          actor="operator", reason=reason)
        inc = self._incidents.get(incident_id)
        if inc is not None:
            inc.status = loop.IncidentStatus.ESCALATED
            inc.escalation_reason = f"rejected by operator: {reason}"
            inc.outcome = "not executed; the operator refused the plan"
            self._remember(inc)
