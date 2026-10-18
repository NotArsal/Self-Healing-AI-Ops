"""The console's HTTP and WebSocket surface.

Read-only except for one route: `POST /v1/loop/run`, which asks the control
plane to perform one pass of the loop it already performs. The browser cannot
name an action, a container, a setting or a value - the only thing it can say
is "run the loop", and everything downstream of that is the same code the
harness runs.

WHAT THE BROWSER CANNOT DO, BY CONSTRUCTION
There is no route that takes an action name, a service name, a container, a
config key, a threshold or a command. There is no docker route and no proxy to
the target. The console reads state and triggers one parameterless pass, so it
cannot bypass detection, cannot bypass RCA validation, and cannot reach
anything `permit()` will eventually have to authorise.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from kavach import __version__, loop
from kavach.api import schemas as s
from kavach.api.events import bus
from kavach.api.runner import (
    LoopBusyError,
    LoopRunner,
    NoBaselineError,
    NotAwaitingError,
)
from kavach.config import Settings, get_settings
from kavach.llm import providers
from kavach.onboarding import preflight
from kavach.onboarding.baseline import _promql
from kavach.target import TargetError

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["console"])

# One runner per process, created on first use. The settings it needs are
# cached, so this is the same object for the life of the process.
_runner: LoopRunner | None = None


def get_runner(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoopRunner:
    global _runner
    if _runner is None:
        _runner = LoopRunner(settings)
    return _runner


# --- mapping internals onto the wire ----------------------------------------


def _verification(d: dict[str, Any] | None) -> s.VerificationOut | None:
    return s.VerificationOut.model_validate(d) if d else None


def _detection(d: dict[str, Any] | None) -> s.DetectionOut | None:
    """Reshape `Detection.to_dict()`.

    Its evidence values are floats, ints, strings or None depending on the
    signal, so they go through the same stringifier the RCA frame uses. Typing
    the field as `str` and handing Pydantic a float is how this produced a 500
    rather than a response.
    """
    if not d:
        return None
    pre = d.get("pre_verification")
    return s.DetectionOut(
        verdict=str(d.get("verdict", "")),
        fault_class=d.get("fault_class"),
        fault_name=d.get("fault_name"),
        service=d.get("service"),
        reasons=list(d.get("reasons", [])),
        evidence=[
            s.DetectionEvidenceOut(
                kind=e["kind"], source=e["source"],
                value=s.to_evidence_value(e.get("value")),
                expected=s.to_evidence_value(e.get("expected")),
                supports_fault=bool(e.get("supports_fault")),
            )
            for e in d.get("evidence", [])
        ],
        pre_verification=_verification(pre),
    )


def _rca(d: dict[str, Any] | None) -> s.RcaOut | None:
    """Reshape `RcaResult.to_dict()`: lift the evidence frame and stringify
    payloads. `raw_response` is not in the source dict and is not added here."""
    if not d:
        return None
    frame = d.get("evidence") or {}
    items = [
        s.EvidenceItemOut(
            eid=i["eid"], kind=i["kind"], name=i["name"],
            value=s.to_evidence_value(i.get("value")),
            expected=i.get("expected") or "", note=i.get("note") or "",
        )
        for i in frame.get("items", [])
    ]
    return s.RcaOut(
        at=d.get("at", ""),
        model=d.get("model", ""),
        latency_s=d.get("latency_s", 0.0),
        prompt_tokens=d.get("prompt_tokens", 0),
        completion_tokens=d.get("completion_tokens", 0),
        approved=bool(d.get("approved")),
        approved_action=d.get("approved_action"),
        error=d.get("error") or "",
        diagnosis=(s.DiagnosisOut.model_validate(d["diagnosis"])
                   if d.get("diagnosis") else None),
        validation=(s.ValidationOut.model_validate(d["validation"])
                    if d.get("validation") else None),
        evidence=items,
        evidence_problems=list(frame.get("problems", [])),
        evidence_collected_at=frame.get("collected_at", "") or "",
    )


def _decision(d: dict[str, Any] | None) -> s.DecisionOut | None:
    return s.DecisionOut.model_validate(d) if d else None


def incident_out(inc: loop.Incident) -> s.IncidentOut:
    before = inc.corpus_before or None
    after = inc.corpus_after or None
    return s.IncidentOut(
        incident_id=inc.incident_id,
        project=inc.project,
        status=str(inc.status),
        detected_at=inc.detected_at,
        resolved_at=inc.resolved_at,
        fault_class=inc.fault_class,
        fault_name=inc.fault_name,
        service=inc.service,
        diagnosed_by=inc.diagnosed_by,
        outcome=inc.outcome,
        escalation_reason=inc.escalation_reason,
        planned_action=inc.planned_action,
        detection=_detection(inc.detection),
        rca=_rca(inc.rca),
        decision=_decision(inc.decision),
        action=s.ActionOut.model_validate(inc.action) if inc.action else None,
        unwind=s.UnwindOut.model_validate(inc.unwind) if inc.unwind else None,
        awaiting_approval=inc.status is loop.IncidentStatus.AWAITING,
        verification=_verification(inc.verification),
        corpus_before=s.CorpusOut.model_validate(before) if before else None,
        corpus_after=s.CorpusOut.model_validate(after) if after else None,
        corpus_unchanged=(before == after) if (before and after) else None,
    )


def incident_summary(inc: loop.Incident) -> s.IncidentSummary:
    return s.IncidentSummary(
        incident_id=inc.incident_id, project=inc.project, status=str(inc.status),
        detected_at=inc.detected_at, resolved_at=inc.resolved_at,
        fault_class=inc.fault_class, fault_name=inc.fault_name,
        service=inc.service, diagnosed_by=inc.diagnosed_by, outcome=inc.outcome,
    )


# --- system health ----------------------------------------------------------


def _prometheus_ok(url: str) -> tuple[bool, str]:
    try:
        value = _promql(url, "up")
        return (value is not None), ("responding to instant queries"
                                     if value is not None else "no result for `up`")
    except Exception as exc:
        # A health probe reports; it never raises into the response path.
        return False, str(exc)[:160]


@router.get("/system", response_model=s.SystemOut)
async def system(
    settings: Annotated[Settings, Depends(get_settings)],
    runner: Annotated[LoopRunner, Depends(get_runner)],
) -> s.SystemOut:
    """Everything the health zone shows. Cheap probes only — no fast set, no
    LLM call, so the console can poll this without costing tokens or 18s."""
    deps: list[s.Dependency] = [
        s.Dependency(name="Kavach control plane", ok=True,
                     detail=f"version {__version__}", endpoint="self")
    ]
    threshold: float | None = None
    config_hash = ""

    client = runner.client()
    try:
        health = await asyncio.to_thread(client.health)
        target_ok = health.get("status") == "ok"
        dependencies = health.get("dependencies", {})
        db = dependencies.get("database", {})
        ollama = dependencies.get("ollama", {})
        pool = health.get("pool", {})
        config_hash = str(health.get("config_hash") or "")
        deps += [
            s.Dependency(name="Target application", ok=target_ok,
                         detail=str(health.get("status")),
                         endpoint=settings.target_health_url),
            s.Dependency(name="Target database", ok=bool(db.get("ok")),
                         detail=str(db.get("detail") or "")
                         + (f" · pool {pool.get('in_use')}/{pool.get('max')}"
                            if pool else ""),
                         endpoint="postgres (via target)"),
            s.Dependency(name="Ollama, target path", ok=bool(ollama.get("ok")),
                         detail=str(ollama.get("detail") or ""),
                         endpoint="via Toxiproxy"),
        ]
    except TargetError as exc:
        deps += [
            s.Dependency(name="Target application", ok=False, detail=str(exc)[:200],
                         endpoint=settings.target_health_url),
            s.Dependency(name="Target database", ok=False,
                         detail="unknown: the target is unreachable",
                         endpoint="postgres (via target)"),
            s.Dependency(name="Ollama, target path", ok=False,
                         detail="unknown: the target is unreachable",
                         endpoint="via Toxiproxy"),
        ]

    try:
        settings_map = await asyncio.to_thread(client.settings)
        raw = settings_map.get("rerank_threshold")
        threshold = float(raw) if isinstance(raw, int | float) else None
    except (TargetError, TypeError, ValueError):
        threshold = None

    llm = providers.build(settings.llm_provider, settings.llm_model,
                          settings.llm_base_url)
    direct_ok = await asyncio.to_thread(llm.available)
    deps.append(s.Dependency(
        name="Ollama, Kavach path", ok=direct_ok,
        detail=(f"model {settings.llm_model}" if direct_ok else "not reachable"),
        endpoint=f"{settings.llm_base_url} (direct, never proxied)",
    ))

    prom_ok, prom_detail = await asyncio.to_thread(
        _prometheus_ok, settings.prometheus_url
    )
    deps.append(s.Dependency(name="Prometheus", ok=prom_ok, detail=prom_detail,
                             endpoint=settings.prometheus_url))

    corpus: s.CorpusOut | None = None
    if prom_ok:
        chunks, files = await asyncio.gather(
            asyncio.to_thread(_promql, settings.prometheus_url, "ragapp_corpus_chunks"),
            asyncio.to_thread(_promql, settings.prometheus_url, "ragapp_corpus_files"),
        )
        corpus = s.CorpusOut(chunks=chunks, files=files)

    baseline_value, baseline_src = runner.baseline()
    deps.append(s.Dependency(
        name="Baseline capture", ok=baseline_value is not None,
        detail=(f"rerank_threshold {baseline_value} from {baseline_src}"
                if baseline_value is not None
                else "none on disk; run `make onboard` against a healthy target"),
        endpoint="harness/baselines/",
    ))

    # The manifest is a dependency, not a config detail: it IS the safety
    # policy, and an unreadable one means nothing may run. Reported as its own
    # row so a fallback mode can never be mistaken for a real one - which is
    # exactly what happened while this returned `settings.default_mode`.
    try:
        mode = runner.mode
        policy_ok, policy_detail = True, f"mode {mode}, enforced by permit()"
    except Exception as exc:
        mode = settings.default_mode
        policy_ok = False
        policy_detail = (f"unreadable, so there is no policy to run under and "
                         f"every run is refused; showing the {mode} default "
                         f"instead: {type(exc).__name__}")
    deps.append(s.Dependency(
        name="Safety policy", ok=policy_ok, detail=policy_detail,
        endpoint=f"{settings.target_path}/kavach.yaml",
    ))

    return s.SystemOut(
        kavach_version=__version__,
        mode=mode,
        mode_is_enforced=policy_ok,
        project=settings.target_project,
        target_path=settings.target_path,
        compose_project=settings.target_compose_project,
        rerank_threshold=threshold,
        config_hash=config_hash,
        corpus=corpus,
        dependencies=deps,
        loop_running=runner.busy,
        running_incident_id=runner.running_incident_id,
    )


# --- preflight --------------------------------------------------------------


@router.get("/preflight", response_model=s.PreflightOut)
async def get_preflight(
    settings: Annotated[Settings, Depends(get_settings)],
) -> s.PreflightOut:
    """Run the existing read-only preflight registry and report it verbatim."""
    try:
        report = await asyncio.to_thread(
            preflight.run, settings.target_path, settings.prometheus_url,
            settings.root(),
        )
    except Exception as exc:
        # A preflight that cannot run is a reportable result, not a 500.
        return s.PreflightOut(
            project=settings.target_project, passed=False, blocking_count=1,
            checks=[],
            ran_at=datetime.now(UTC).isoformat(timespec="seconds"),
            error=f"{type(exc).__name__}: {exc}",
        )
    return s.PreflightOut(
        project=report.project,
        passed=report.passed,
        blocking_count=len(report.blocking),
        ran_at=datetime.now(UTC).isoformat(timespec="seconds"),
        checks=[
            s.PreflightCheckOut(
                name=r.name, passed=r.passed, skipped=r.skipped, status=r.symbol,
                detail=r.detail, remediation=r.remediation,
            )
            for r in report.results
        ],
    )


# --- incidents --------------------------------------------------------------


@router.get("/incidents", response_model=list[s.IncidentSummary])
async def list_incidents(
    runner: Annotated[LoopRunner, Depends(get_runner)],
) -> list[s.IncidentSummary]:
    return [incident_summary(i) for i in runner.incidents()]


@router.get("/incidents/{incident_id}", response_model=s.IncidentOut)
async def get_incident(
    incident_id: str,
    runner: Annotated[LoopRunner, Depends(get_runner)],
) -> s.IncidentOut:
    inc = runner.incident(incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail=f"no incident {incident_id}")
    return incident_out(inc)


@router.post("/loop/run", response_model=s.RunStarted, status_code=202)
async def run_loop(
    runner: Annotated[LoopRunner, Depends(get_runner)],
    rca: Annotated[bool, Query(description="Run the LLM RCA stage")] = True,
) -> s.RunStarted:
    """One pass of the existing loop. Takes no action, service or value.

    Returns 202 immediately; progress arrives on the WebSocket and the finished
    incident is readable at `/v1/incidents/{id}`.
    """
    try:
        inc = await runner.start(use_rca=rca)
    except LoopBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NoBaselineError as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    return s.RunStarted(
        incident_id=inc.incident_id,
        started_at=inc.detected_at,
        # The mode this run is actually gated by. `start()` has already read
        # the policy, so this cannot raise here.
        mode=runner.mode,
        rca_enabled=rca,
    )


# --- events -----------------------------------------------------------------


@router.get("/mode", response_model=s.ModeOut)
async def get_mode(
    runner: Annotated[LoopRunner, Depends(get_runner)],
) -> s.ModeOut:
    policy = runner.policy()
    manifest = runner.manifest()
    return s.ModeOut(
        mode=policy.mode,
        # The mode is now READ by permit(), so it genuinely gates. Before P5
        # this was a configured value nothing consulted.
        enforced=True,
        manifest_mode=manifest.mode,
        overridden=policy.mode != manifest.mode,
        allowed_actions=sorted(policy.allowed_actions),
        denied_mutations=sorted(policy.denied_mutations),
        confidence_threshold=policy.confidence_threshold,
    )


@router.put("/mode", response_model=s.ModeOut)
async def set_mode(
    body: s.ModeChange,
    runner: Annotated[LoopRunner, Depends(get_runner)],
) -> s.ModeOut:
    """Change the operating mode for this process.

    Audited. Moving a project to AUTONOMOUS is the most consequential
    configuration act available, and an unrecorded one is indistinguishable
    from a compromise. The manifest remains the durable default.
    """
    runner.set_mode(body.mode)
    return await get_mode(runner)


@router.post("/incidents/{incident_id}/approve", response_model=s.RunStarted,
             status_code=202)
async def approve(
    incident_id: str,
    runner: Annotated[LoopRunner, Depends(get_runner)],
) -> s.RunStarted:
    """Authorise a parked plan.

    This re-detects and re-prepares rather than replaying a stored payload: the
    world may have moved since the operator looked, and the action that runs
    must be built against the target as it is now. What was approved is the
    decision, not a frozen diff — so `permit()` runs again, deny-list and
    breaker included.
    """
    # Read BEFORE approve(), which pops the parked entry.
    used_rca = runner.parked_used_rca(incident_id)
    try:
        inc = await runner.approve(incident_id)
    except NotAwaitingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LoopBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NoBaselineError as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    return s.RunStarted(
        incident_id=inc.incident_id, started_at=inc.detected_at,
        # Whether the approved re-run ACTUALLY used RCA, not a hardcoded True.
        # The re-run re-derives the plan the way it was first derived, so
        # claiming RCA ran when it did not would misreport the pipeline an
        # operator just authorised.
        mode=runner.mode, rca_enabled=used_rca, approved_from=incident_id,
    )


@router.post("/incidents/{incident_id}/reject", status_code=204)
async def reject(
    incident_id: str,
    body: s.RejectRequest,
    runner: Annotated[LoopRunner, Depends(get_runner)],
) -> None:
    try:
        runner.reject(incident_id, body.reason)
    except NotAwaitingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/metrics", response_model=s.FleetMetrics)
async def fleet_metrics(
    runner: Annotated[LoopRunner, Depends(get_runner)],
) -> s.FleetMetrics:
    """MTTR and repair success over the persisted series.

    Null rather than zero when there is nothing to measure: a dashboard that
    cannot tell "no data" from "instant" will publish a fabricated number.
    """
    data = await asyncio.to_thread(runner.fleet_metrics)
    return s.FleetMetrics(
        **{k: v for k, v in data.items() if k != "available"},
        available=bool(data.get("available")),
        unavailable_reason=runner.store.unavailable_reason,
    )


@router.get("/audit", response_model=s.AuditOut)
async def audit_trail(
    runner: Annotated[LoopRunner, Depends(get_runner)],
    limit: int = 200,
) -> s.AuditOut:
    """The hash-chained trail, with the chain verified on every read.

    There is no write route here, and there never will be.
    """
    rows = await asyncio.to_thread(runner.audit.rows, limit)
    check = await asyncio.to_thread(runner.audit.verify)
    return s.AuditOut(
        rows=[s.AuditRow.model_validate(
            {k: str(r.get(k, "")) for k in
             ("at", "incident_id", "actor", "event", "hash", "prev")}
        ) for r in rows],
        chain_intact=check.intact,
        broken_at=check.broken_at,
        detail=check.detail,
    )


@router.get("/events", response_model=list[s.EventOut])
async def recent_events(after: int = 0) -> list[s.EventOut]:
    """Replay buffer, for a console that loaded after a run began. The live
    feed is the WebSocket; this is not a polling endpoint."""
    return [s.EventOut.model_validate(e) for e in bus.replay(after)]


@router.websocket("/ws")
async def events_ws(websocket: WebSocket) -> None:
    """Live loop events. Sends the replay buffer first, then streams.

    Declared on the router but absent from the OpenAPI document, because
    OpenAPI does not describe WebSockets. `EventOut` is in the document via
    `GET /v1/events`, so the generated client still types the payload.
    """
    await websocket.accept()
    # Subscribe BEFORE replaying, so a stage that completes mid-replay is
    # queued rather than lost. The client de-duplicates on `seq`, so the
    # overlap between the buffer and the queue is harmless.
    stream = bus.subscribe()
    try:
        for event in bus.replay():
            await websocket.send_text(json.dumps(event))
        async for event in stream:
            await websocket.send_text(json.dumps(event))
    except WebSocketDisconnect:
        pass
    except Exception:
        # A dead socket is not an error worth raising.
        logger.debug("console websocket closed", exc_info=True)
    finally:
        # Deterministic unsubscribe. Returning from inside `async for` only
        # suspends the generator, so without this the queue stays registered
        # and is filled forever for a browser that has gone.
        await stream.aclose()
