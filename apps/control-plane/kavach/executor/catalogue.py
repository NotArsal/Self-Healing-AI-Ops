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

from kavach.executor import config_rollback, endpoint_switch, prompt_rollback
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

# `apply_patch` is NOT registered, and as of 2026-10-18 it never will be in
# v1: P7 is cut (`docs/decisions/0009-p7-is-cut.md`), which takes the sandbox
# and this action with it - they were always one decision, per ROADMAP's P6
# cut line. The paragraph below is kept because the REASON it is unregistered
# is the point, and it outlives the schedule that once said "P7".
#
# `apply_patch` is NOT registered. Its contract exists (ARCHITECTURE.md §6.2.1)
# and its tier is fixed HIGH, but it requires the sandbox, and registering an
# action whose safety precondition is unbuilt would make `permit()` able to
# authorise something that cannot yet be made safe. It would have
# registered with `tier_is_fixed=True`; it now does not register at all,
# which is the behaviour that matters - an unregistered action cannot be
# authorised by permit() whatever any document says.

__all__ = ["registry"]
