"""Action registration — the one place the catalogue is assembled.

Importing this module populates the registry. Nothing else registers actions,
so `registry.names()` is a complete and auditable answer to "what can Kavach
do", which `permit()` and the console both need.

THIS IS THE SEAM THAT REMOVES THE RAG COUPLING
`loop.py` used to import `build_rollback_for_retrieval_collapse` by name, which
made the generic orchestrator a RAG orchestrator (`ARCHITECTURE.md` §1.4). It
now asks the registry for an action by the name the planner chose. The repair
stays exactly as it was; what changes is that the loop no longer knows which
workload it belongs to.

Adding a workload means adding a line here, not editing the loop.
"""

from __future__ import annotations

from kavach.executor import (
    apply_patch,
    config_rollback,
    endpoint_switch,
    prompt_rollback,
)
from kavach.executor.base import HIGH, LOW, MEDIUM, registry

registry.register(
    name=config_rollback.ACTION_NAME,
    builder=config_rollback.build_rollback_for_retrieval_collapse,
    risk_tier=MEDIUM,
    action_type=config_rollback.ConfigRollback,
)

# F01's repair, added 2026-10-16. Same `ConfigRollback` machinery, built with a
# different name and tier - see `endpoint_switch.py` for why that is a builder
# rather than a second action class. LOW because it moves the application
# between two listeners in front of the SAME model: no data, no prompts, no
# answers change, and the recorded prior URL restores it exactly. LOW is also
# the only tier `permit()` executes unattended, so this is the action that
# makes the autonomous path in `PRD.md` §8.2 real rather than theoretical.
registry.register(
    name=endpoint_switch.ACTION_NAME,
    builder=endpoint_switch.build_switch_for_endpoint_outage,
    risk_tier=LOW,
    action_type=config_rollback.ConfigRollback,
)

# F07's repair, added 2026-10-17. The FIRST action that writes a file rather
# than a config key, which is why it is its own class instead of another
# `ConfigRollback` construction: the write path, the witness and all three
# verifications are different, and only the contract is shared. MEDIUM for the
# same reason `rollback_config` is - it changes answer quality and is
# reversible from a recorded witness.
registry.register(
    name=prompt_rollback.ACTION_NAME,
    builder=prompt_rollback.build_rollback_for_prompt_regression,
    risk_tier=MEDIUM,
    action_type=prompt_rollback.PromptRollback,
)

# `apply_patch`, added 2026-10-18. ADR 0011 partially reverses ADR 0009: the
# sandbox and this action are restored, Laya and the knowledge base stay cut.
#
# The ONLY action whose payload a model wrote, and the only HIGH one.
# `tier_is_fixed=True` says that tier is a property of the action and not of
# its parameters - there is no patch small enough, and no file harmless
# enough, to make a generated write MEDIUM. Every other action picks a name
# from a closed list and writes a recorded value; this one writes prose that
# did not exist until a model produced it.
#
# ADR 0009's objection to registering it was precise and is now answered: an
# action whose safety precondition is unbuilt would let `permit()` authorise
# something that cannot be made safe. The sandbox is built and proven, and
# `ApplyPatch.prepare()` will not return an action at all unless the patch has
# already been applied to a clone and passed the fast set there. So by the
# time `permit()` sees this, constraint 4 has a real answer rather than a
# promise - which is why the trial lives in `prepare()` and not in `execute()`.
registry.register(
    name=apply_patch.ACTION_NAME,
    builder=apply_patch.build_from_proposal,
    risk_tier=HIGH,
    action_type=apply_patch.ApplyPatch,
    tier_is_fixed=True,
)

__all__ = ["registry"]
