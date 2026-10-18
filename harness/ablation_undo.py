"""The undo-stack ablation: what does the inverse actually buy?

`PRD.md` §10.3 asks for "the catalogue with the undo stack disabled" and
calls reproducing the shape of STRATUS's equivalent ablation the strongest
research contribution available here. This is that run.

THE FINDING THAT CAME FIRST, AND IT CHANGES WHAT THE ABLATION CAN CLAIM
**The undo stack has never fired.** Across every live gate, every stability
run and every recorded artifact in `harness/reports/`, there is not one
`unwind` event. Every repair this system has executed has worked, so the
inverse has never been needed. `p5_gate_live.py`'s
`unwound_cleanly_when_verification_failed` passes *trivially* whenever the
repair resolves - it only inspects the unwind if verification failed, and
verification never has.

So the honest ablation is not "measure how much better the system is with
undo", because on the observed catalogue the answer is zero: both arms would
resolve identically. It is: **construct the case the undo stack exists for,
and show what each arm leaves behind.** An insurance policy is measured by
what happens on the one day it is claimed.

THE SCENARIO IS REAL, NOT RIGGED
Both LLM paths down at once. `F01`'s repair is `switch_llm_endpoint`, which
fails the application over from the primary Toxiproxy listener to the backup.
If the backup is down too, the repair is correctly chosen, correctly applied,
and still does not work - so verification genuinely fails on its own terms.
Nothing is mocked, no check is weakened, and "both paths to the model are
unreachable" is an ordinary outage, not a contrivance.

This matters because the alternative was faking it: monkeypatching the target
to stay broken, as the offline tests do, would measure the mock rather than
the system.

WHAT IS AND IS NOT ABLATED
The ablation disables ONE thing: `UndoStack.unwind`, replaced with a no-op in
this process only. No production code is modified, no flag is added to the
shipped system, and nothing persists beyond the run. A "disable the undo
stack" switch in deployable code would be a weakened safety mechanism
shipped for the sake of an experiment, which is exactly what `AGENTS.md`
forbids.

`permit()` runs in full in both arms. The policy object is built here with
`mode=AUTONOMOUS` so that `F01`'s LOW-risk repair executes without a human,
which is the documented autonomous path (`PRD.md` §8.2) - the deployed
manifest and the running API's mode are not touched.

    uv run --project apps/control-plane python -I harness/ablation_undo.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE = ROOT / "apps" / "control-plane"
sys.path[:0] = [str(ROOT), str(CONTROL_PLANE)]

from harness.faults.f01_endpoint_outage import (  # noqa: E402
    BACKUP,
    F01EndpointOutage,
)
from kavach import loop as loop_mod  # noqa: E402
from kavach.api.runner import newest_baseline_doc, policy_from_manifest  # noqa: E402
from kavach.config import get_settings  # noqa: E402
from kavach.executor import catalogue as _actions  # noqa: E402, F401
from kavach.executor import undo_stack as undo_mod  # noqa: E402
from kavach.executor.base import registry as action_registry  # noqa: E402
from kavach.loop import run_once  # noqa: E402
from kavach.onboarding.manifest import load as load_manifest  # noqa: E402
from kavach.safety.engine import SafetyEngine  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402

FAST_SET = CONTROL_PLANE / "kavach" / "verification" / "fast_set.yaml"
TARGET = "http://127.0.0.1:8000"
PROM = "http://127.0.0.1:9091"
TOXI = "http://127.0.0.1:8474"


def say(m: str = "") -> None:
    print(m, flush=True)


def promql(_url: str, query: str) -> float | None:
    url = PROM + "/api/v1/query?query=" + urllib.parse.quote(query)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            res = json.loads(r.read())["data"]["result"]
        return float(res[0]["value"][1]) if res else None
    except Exception:
        return None


def proxy(name: str, enabled: bool) -> None:
    body = json.dumps({"enabled": enabled}).encode()
    req = urllib.request.Request(f"{TOXI}/proxies/{name}", data=body,
                                 method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10):
        pass


def proxy_state() -> dict[str, bool]:
    with urllib.request.urlopen(TOXI + "/proxies", timeout=10) as r:
        return {k: bool(v["enabled"]) for k, v in json.loads(r.read()).items()}


class AblatedUndoStack(undo_mod.UndoStack):
    """An `UndoStack` that records the request and refuses to restore.

    `attempted=0, restored=0` with an explicit failure line, so the artifact
    shows the stack WAS reached and declined - distinguishable from a run
    where verification passed and no unwind was ever needed. That
    distinction is the whole measurement.
    """

    def unwind(self, _client: TargetClient) -> undo_mod.UnwindReport:
        return undo_mod.UnwindReport(
            attempted=0, restored=0,
            failures=[f"ABLATED: undo disabled; {self.depth} action(s) "
                      f"left applied"],
        )


@dataclass
class Arm:
    undo_enabled: bool
    status: str = ""
    fault_class: str = ""
    action: str = ""
    executed: bool = False
    unwind_attempted: int = 0
    unwind_restored: int = 0
    unwind_clean: bool | None = None
    endpoint_before: str = ""
    endpoint_after: str = ""
    restored_to_pre_state: bool = False
    outcome: str = ""
    error: str = ""


def run_arm(undo_enabled: bool, client: TargetClient) -> Arm:
    arm = Arm(undo_enabled=undo_enabled)
    settings = get_settings()
    manifest = load_manifest(Path(settings.target_path) / "kavach.yaml")
    policy = policy_from_manifest(manifest, "AUTONOMOUS")
    baseline, _ = newest_baseline_doc(settings.baselines_dir(),
                                      settings.target_project)
    backup_url = manifest.llm.paths.backup if manifest.llm and manifest.llm.paths else None

    fault = F01EndpointOutage()
    real_stack_cls = loop_mod.UndoStack  # type: ignore[attr-defined]
    try:
        arm.endpoint_before = str(client.settings()["llm_base_url"])

        # The scenario: BOTH paths to the model are down. The repair is still
        # the right one and still will not work.
        fault.inject()                      # primary down
        proxy(BACKUP, False)                # backup down too
        say(f"    proxies: {proxy_state()}")

        if not undo_enabled:
            # THE ABLATION, and it is a subclass rather than a patched
            # method on purpose: a subclass states in its own signature that
            # it is an UndoStack that does not unwind, and the type checker
            # holds it to the real contract. `loop.py` imported the name
            # directly, so the swap is on `kavach.loop`, and it is undone in
            # the finally block below. Nothing in the shipped system changes.
            loop_mod.UndoStack = AblatedUndoStack  # type: ignore[attr-defined]

        inc = run_once(
            client, PROM, FAST_SET, promql,
            baseline_value=baseline.get("rerank_threshold", 0.35),
            safety=SafetyEngine(action_registry), policy=policy,
            repair_values={"switch_llm_endpoint": backup_url} if backup_url else None,
            baseline=baseline,
        )
        arm.status = str(inc.status)
        arm.fault_class = inc.fault_class or ""
        arm.action = inc.planned_action or ""
        arm.executed = bool((inc.action or {}).get("executed"))
        arm.outcome = (inc.outcome or "")[:200]
        if inc.unwind:
            arm.unwind_attempted = int(inc.unwind.get("attempted", 0))
            arm.unwind_restored = int(inc.unwind.get("restored", 0))
            arm.unwind_clean = bool(inc.unwind.get("clean"))
    except Exception as exc:
        arm.error = f"{type(exc).__name__}: {exc}"
    finally:
        loop_mod.UndoStack = real_stack_cls  # type: ignore[attr-defined]
        # Read the endpoint BEFORE restoring anything: this is the measurement.
        try:
            arm.endpoint_after = str(client.settings()["llm_base_url"])
            arm.restored_to_pre_state = arm.endpoint_after == arm.endpoint_before
        except Exception as exc:
            arm.error = (arm.error + f" | read-back failed: {exc}").strip(" |")
        # Now put everything back, whatever happened.
        try:
            fault.revert()
            proxy(BACKUP, True)
            client.apply_settings({"llm_base_url": arm.endpoint_before})
        except Exception as exc:
            arm.error = (arm.error + f" | restore failed: {exc}").strip(" |")
    return arm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out",
                    default=str(ROOT / "harness" / "reports" / "ablation-undo.json"))
    args = ap.parse_args()

    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", "")))

    say("=" * 78)
    say("UNDO-STACK ABLATION: both LLM paths down, so the right repair fails")
    say("=" * 78)
    say(f"  starting proxies   {proxy_state()}")
    say(f"  starting endpoint  {client.settings()['llm_base_url']}")
    say("")

    arms: list[Arm] = []
    for undo_enabled in (True, False):
        label = "WITH undo" if undo_enabled else "WITHOUT undo (ablated)"
        say("-" * 78)
        say(f"  {label}")
        say("-" * 78)
        arm = run_arm(undo_enabled, client)
        arms.append(arm)
        say(f"    diagnosed          {arm.fault_class} -> {arm.action}")
        say(f"    executed           {arm.executed}")
        say(f"    status             {arm.status}")
        say(f"    unwind             attempted={arm.unwind_attempted} "
            f"restored={arm.unwind_restored} clean={arm.unwind_clean}")
        say(f"    endpoint           {arm.endpoint_before} -> {arm.endpoint_after}")
        say(f"    back to pre-state  {arm.restored_to_pre_state}")
        if arm.error:
            say(f"    error              {arm.error}")
        say("")
        time.sleep(5)

    say("=" * 78)
    say("RESULT")
    say("=" * 78)
    with_undo = arms[0]
    without = arms[1]
    say(f"  {'':<22} {'WITH undo':<28} {'WITHOUT undo':<28}")
    say(f"  {'repair executed':<22} {with_undo.executed!s:<28} "
        f"{without.executed!s:<28}")
    say(f"  {'verification':<22} {'failed (both paths down)':<28} "
        f"{'failed (both paths down)':<28}")
    say(f"  {'endpoint left at':<22} {with_undo.endpoint_after:<28} "
        f"{without.endpoint_after:<28}")
    say(f"  {'target as found':<22} {with_undo.restored_to_pre_state!s:<28} "
        f"{without.restored_to_pre_state!s:<28}")
    say("")

    difference = with_undo.restored_to_pre_state and not without.restored_to_pre_state
    if difference:
        say("  THE ABLATION SHOWS A DIFFERENCE. With the undo stack, a repair "
            "that did not work leaves the target exactly as it was found. "
            "Without it, the target is left in a THIRD state - neither the "
            "fault that was diagnosed nor the health that was wanted - and no "
            "record says which.")
    else:
        say("  NO DIFFERENCE OBSERVED between the arms. That is a result, not "
            "a failed run: report it as measured rather than assuming the "
            "undo stack earned its place.")

    say("")
    say("  CONTEXT THE REPORT MUST CARRY: across every live gate, stability "
        "run and artifact before this one, the undo stack had never fired. "
        "This run constructed the case it exists for. Its value here is "
        "insurance against a case that had not occurred naturally, which is "
        "a weaker claim than a measured improvement and should be written "
        "as one.")

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scenario": "both toxiproxy listeners disabled; F01 repair cannot work",
        "unwind_events_before_this_run": 0,
        "arms": [asdict(a) for a in arms],
        "difference_observed": difference,
    }, indent=2, default=str) + "\n", encoding="utf-8")
    say(f"  artifact {out}")
    say(f"  final proxies {proxy_state()}")
    say(f"  final endpoint {client.settings()['llm_base_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
