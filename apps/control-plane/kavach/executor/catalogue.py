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

from kavach.executor import config_rollback, endpoint_switch
from kavach.executor.base import LOW, MEDIUM, registry

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

# `apply_patch` is NOT registered. Its contract exists (ARCHITECTURE.md §6.2.1)
# and its tier is fixed HIGH, but it requires the sandbox, and registering an
# action whose safety precondition is unbuilt would make `permit()` able to
# authorise something that cannot yet be made safe. It registers in P7, with
# `tier_is_fixed=True`.

__all__ = ["registry"]
