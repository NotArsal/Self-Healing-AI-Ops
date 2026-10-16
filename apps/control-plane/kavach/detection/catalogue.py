"""Detector registration — the one place the catalogue is assembled.

Importing this module populates the registry. Nothing else registers detectors,
so `registry.fault_classes()` is a complete and auditable answer to "what can
Kavach see", exactly as `executor/catalogue.py` answers "what can Kavach do".

THIS IS THE OTHER HALF OF THE SEAM
`executor/catalogue.py` removed the loop's hardcoded import of one repair.
This removes its hardcoded import of one detector and the `KNOWN_FAULTS` table
that sat in the orchestrator's own module body mapping one fault class to one
action. The loop now asks the registry what to look for and what repairs it.

Adding a fault class means adding a line here, not editing the loop. F01 was
the first fault added after P5 and `ROADMAP.md` set it as the test of whether
these seams existed: it needed this module built, and then needed no change to
`loop.py`'s decision logic, `rca/schema.py`, `llm/`, or the safety engine.

ORDER IS REGISTRATION ORDER, BUT IT IS NOT A PRIORITY
`run_all()` evaluates every detector and refuses to choose when two claim at
once, so this list's order never decides a diagnosis. It is listed cheapest
first only because that is the order a human would read them in.
"""

from __future__ import annotations

from kavach.detection import config_regression, endpoint_outage, retrieval_collapse
from kavach.detection.base import registry

# F01 — the endpoint is visibly down; HTTP status carries the fault.
registry.register(endpoint_outage.SPEC)

# F06 — the endpoint is up and the answers are wrong; HTTP status carries
# nothing, and detection has to come from grounding metrics.
registry.register(retrieval_collapse.SPEC)

# F08 — a setting drifted from the captured known-good and nothing more
# specific explains it. Listed LAST because it is the residual config class,
# and it defers to the others by ownership rather than by position: see
# `config_regression.CLAIMED_ELSEWHERE`. Position here still decides nothing,
# because `run_all()` refuses to choose when two detectors claim at once.
registry.register(config_regression.SPEC)

__all__ = ["registry"]
