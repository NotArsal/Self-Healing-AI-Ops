"""
Decision / Safety Engine — deterministic policy evaluation.

This is NOT an LLM. It receives a proposed repair action from the
Repair Planner and returns a safety decision based on hard-coded rules:
  - LOW risk  → auto-execute
  - MEDIUM risk → sandbox / canary first
  - HIGH risk  → human approval required

It also enforces:
  - Action allowlist (only permitted Kubernetes operations)
  - Rate limiting (max 5 auto-actions per 10 minutes per service)
  - Kill switch (if SAFETY_KILL_SWITCH env var is set, block everything)
"""

import os
import logging
import time
from collections import defaultdict
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

# ─── Configuration ─────────────────────────────────────────────────────────────

KILL_SWITCH_ACTIVE = os.environ.get("SAFETY_KILL_SWITCH", "false").lower() == "true"

# Only these Kubernetes actions are ever permitted
ACTION_ALLOWLIST = {
    "restart_deployment",
    "scale_deployment",
    "rollback",
}

RISK_THRESHOLDS = {
    "LOW":    "auto",
    "MEDIUM": "sandbox",
    "HIGH":   "approval_required",
}

# Rate-limit: max auto-actions per service in a rolling window
MAX_AUTO_ACTIONS = 5
RATE_WINDOW_SECONDS = 600

# In-memory rate-limit buckets {service: [(timestamp)]}
_rate_buckets: Dict[str, list] = defaultdict(list)


# ─── Public API ───────────────────────────────────────────────────────────────

def evaluate(
    action: Dict[str, Any],
    affected_service: str,
) -> Tuple[str, str]:
    """
    Evaluate whether a proposed action is permitted.

    Returns:
        (decision, reason)  where decision is one of:
        "auto" | "sandbox" | "approval_required" | "blocked"
    """

    # 1. Kill switch
    if KILL_SWITCH_ACTIVE:
        return "blocked", "Safety kill switch is active. All actions blocked."

    # 2. Allowlist check
    action_name = action.get("action", "")
    if action_name not in ACTION_ALLOWLIST:
        return "blocked", f"Action '{action_name}' is not on the allowlist."

    # 3. Risk-level routing
    risk = action.get("risk", "HIGH")
    decision = RISK_THRESHOLDS.get(risk, "approval_required")

    # 4. Rate-limit check for auto actions
    if decision == "auto":
        now = time.time()
        # Prune old entries outside the window
        _rate_buckets[affected_service] = [
            t for t in _rate_buckets[affected_service]
            if now - t < RATE_WINDOW_SECONDS
        ]
        if len(_rate_buckets[affected_service]) >= MAX_AUTO_ACTIONS:
            logger.warning(
                f"Rate limit hit for {affected_service}: "
                f"{len(_rate_buckets[affected_service])} actions in last {RATE_WINDOW_SECONDS}s"
            )
            decision = "approval_required"
            return decision, f"Rate limit exceeded for {affected_service}. Human approval required."

        # Record this action
        _rate_buckets[affected_service].append(now)

    reason = {
        "auto":              f"Action '{action_name}' is LOW risk and within rate limits. Auto-executing.",
        "sandbox":           f"Action '{action_name}' is MEDIUM risk. Routing to sandbox validation first.",
        "approval_required": f"Action '{action_name}' is HIGH risk. Requires human operator approval.",
    }.get(decision, "Unknown decision.")

    logger.info(f"[SafetyEngine] Service={affected_service} Action={action_name} Decision={decision}")
    return decision, reason
