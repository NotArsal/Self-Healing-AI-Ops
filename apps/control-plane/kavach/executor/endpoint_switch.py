"""`switch_llm_endpoint` — fail the application over to its declared backup.

THERE IS ALMOST NO CODE HERE, AND THAT IS THE POINT
`ConfigRollback` is already generic over *which settings* it writes: it reads
the live config, captures the prior value of every key it is about to touch,
writes through the target's validated interface, and inverts by replaying the
captured witness. A failover is one more key written through that same
interface — `llm_base_url` is in `control_interface.settable` — so this module
is a builder, not a second action class.

Writing a near-duplicate class would have duplicated the two properties that
actually matter (the inverse is a recorded value, and there is no shell) into a
second place where they could drift apart. The name and the risk tier are
dataclass fields on `ConfigRollback`, so a LOW-risk `switch_llm_endpoint` is a
different *construction* of the same verified machinery, not a different
mechanism.

WHY LOW, WHEN `rollback_config` IS MEDIUM
Both write one config key. The difference is what the key does.
`rerank_threshold` changes retrieval behaviour and therefore answer quality,
which is why §6.2 calls it MEDIUM. `llm_base_url` moves the application to a
second listener in front of the SAME model: nothing about the model, the
prompts, the corpus or the answers changes, and the prior URL restores it
exactly. §6.2's table lists `switch_llm_endpoint` as LOW on that reasoning —
config-only, instantly reversible, no data touched — and LOW is what gives
`PRD.md` §8.2 its autonomous path, because LOW is the one tier `permit()`
returns ALLOW_AUTO for in AUTONOMOUS mode.

THE BACKUP URL IS DECLARED, NEVER DERIVED OR GUESSED
It comes from the manifest's `llm.paths.backup`. The project's rule is that an
inverse is a recorded value rather than a constant; the same discipline applies
to the *forward* value here, because a hardcoded failover URL would be a
control-plane module knowing a workload's network topology. A workload that
declares no backup cannot be failed over, and `prepare()` refuses rather than
inventing one — the same stance `ConfigRollback` takes when no baseline was
captured.

IT IS ALSO NOT THE INJECTOR'S INVERSE
F01 is injected by disabling the primary Toxiproxy listener. The repair is a
switch to the backup listener, NOT re-enabling the primary. Re-enabling would
be the injector undoing itself, which demonstrates nothing about healing: the
system must route around the failure using only what the application itself can
be told to do through its own control interface.
"""

from __future__ import annotations

from kavach.executor.config_rollback import ActionError, ConfigRollback

ACTION_NAME = "switch_llm_endpoint"
RISK_TIER = "LOW"  # config-only, instantly reversible, no data touched

# The one setting this action writes. Declared so the deny-list check in
# `permit()` sees a concrete parameter rather than an opaque action name.
SETTING = "llm_base_url"


def build_switch_for_endpoint_outage(
    incident_id: str,
    client: object,
    backup_url: str | None = None,
) -> ConfigRollback:
    """Prepare a failover to the declared backup endpoint.

    `backup_url` is the manifest's `llm.paths.backup`. None means the workload
    declares no second path, which is a refusal rather than a default: failing
    over to a guessed address is a write into the dark.

    Signature mirrors `build_rollback_for_retrieval_collapse` so the registry
    can build either by name with the same call shape.
    """
    if not backup_url:
        raise ActionError(
            "no backup LLM endpoint is declared for this project "
            "(`llm.paths.backup` in its manifest is null), so there is nowhere "
            "to fail over to. A guessed address would be a write into the dark"
        )

    action = ConfigRollback(
        incident_id=incident_id,
        target_settings={SETTING: backup_url},
        name=ACTION_NAME,
        risk_tier=RISK_TIER,
    )
    # prepare() captures the CURRENT llm_base_url as the inverse, so the
    # rollback target is wherever the application was actually pointed - not
    # the manifest's `primary`, which can be stale. It was, in fact, stale:
    # `llm.paths.primary` named host.docker.internal:11434 while the running
    # backend used toxiproxy:21434, and a witness read from the manifest rather
    # than the live target would have restored the wrong endpoint.
    action.prepare(client)  # type: ignore[arg-type]

    if action.inverse_settings.get(SETTING) == backup_url:
        raise ActionError(
            f"the application is already pointed at {backup_url!r}, so a "
            f"failover would be a no-op and its inverse would restore the "
            f"faulty endpoint. The backup is not a second fault's repair"
        )
    return action
