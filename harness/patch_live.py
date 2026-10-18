"""P7 live: a model writes a repair, and it is tried on a clone.

This is the first time anything generated reaches a running system, and the
only reason it is safe to run is that the running system it reaches is the
sandbox.

WHAT IT DOES
    1. inject F07 - degrade the target's `answer.txt` for real
    2. collect an evidence frame and diagnose with the real model
    3. ask the model for a PATCH to `answer.txt`
    4. build the action, which applies that patch to the SANDBOX and runs
       the sandbox's fast set there
    5. report, revert the injector, and stop

WHAT IT DELIBERATELY DOES NOT DO
It never calls `execute()`. Promoting a sandbox-proven patch to production is
slice 4 and needs a human approval path that does not exist yet. So this
harness proves the thing P7 was cut for not having - that a generated repair
can be produced and TESTED without risk - and stops exactly where the risk
would begin.

THE SHAPE OF A PASS
Production stays degraded throughout; the sandbox, with the generated patch
applied, passes its fast set. The two systems disagree, and that disagreement
is the whole value of a sandbox: it is evidence about the patch that cost
production nothing.

A FAILURE HERE IS A RESULT, NOT A BUG
If the model cannot write a patch that restores grounding, that is a finding
about small local models writing repairs, and it is reported as one. The
measurement is not retried with a nudged prompt (`rca/patch_engine.py` says
why), and the threshold is not moved.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE = ROOT / "apps" / "control-plane"
sys.path[:0] = [str(ROOT), str(CONTROL_PLANE)]

from harness.faults.f07_prompt_regression import (  # noqa: E402
    PROMPT_FILE,
    F07PromptRegression,
)
from kavach.config import get_settings  # noqa: E402
from kavach.detection import catalogue  # noqa: E402, F401 - registers detectors
from kavach.executor import apply_patch, sandbox  # noqa: E402
from kavach.executor.config_rollback import ActionError  # noqa: E402
from kavach.llm.client import OllamaClient  # noqa: E402
from kavach.onboarding.manifest import load as load_manifest  # noqa: E402
from kavach.rca import patch_engine  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402
from kavach.verification import fast  # noqa: E402

TARGET = "http://127.0.0.1:8000"
FAST_SET = CONTROL_PLANE / "kavach" / "verification" / "fast_set.yaml"


def say(m: str = "") -> None:
    print(m, flush=True)


def probe(model: str, ollama: str, n: int, json_out: str) -> int:
    """How often does this model write a patch that actually applies?

    Separated from the live run because it needs no target, no sandbox and
    no injection: it asks the one question that turned out to be decisive,
    and asks it cheaply enough to ask of several models.

    A patch is counted ONLY if `git apply --check` accepts it against the
    degraded file. Passing the deterministic checks is not counted as
    success - every model passes those, and a well-formed diff that does
    not fit the file repairs nothing.
    """
    import tempfile

    from harness.faults.f07_prompt_regression import DEGRADED_PROMPT
    from kavach.executor.adapters import git
    from kavach.llm.client import LlmError
    from kavach.rca.patch_schema import ollama_schema

    schema = ollama_schema(["prompts/answer.txt"])
    prompt = patch_engine.build_prompt(
        {"fault_class": "F07", "service": "backend", "confidence": 0.9},
        "EV-C08 prompt answer.txt changed from baseline; grounding absent",
        f"prompts/{PROMPT_FILE}", DEGRADED_PROMPT)
    llm = OllamaClient(ollama, model)

    applies = 0
    failures: list[str] = []
    for _ in range(n):
        try:
            raw = llm.structured(
                system="You propose one small, reversible edit to one text file.",
                user=prompt, schema=schema).raw
            diff = str(json.loads(raw).get("diff", ""))
        except (LlmError, ValueError) as exc:
            failures.append(f"generation: {exc}")
            continue
        with tempfile.TemporaryDirectory() as t:
            area = Path(t)
            (area / PROMPT_FILE).write_text(
                DEGRADED_PROMPT, encoding="utf-8", newline="")
            try:
                git.check(diff, area, area, strip=2)
                applies += 1
            except git.GitAdapterError as exc:
                failures.append(str(exc)[:160])

    say(f"{model}: {applies}/{n} patches apply to the file")
    for f in failures[:3]:
        say(f"   {f}")
    Path(json_out).parent.mkdir(parents=True, exist_ok=True)
    Path(json_out).write_text(json.dumps(
        {"model": model, "runs": n, "applies": applies,
         "failures": failures[:10],
         "measured": datetime.now(UTC).isoformat(timespec="seconds")},
        indent=2), encoding="utf-8", newline="")
    return 0 if applies else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--json-out",
                    default=str(ROOT / "harness" / "reports" / "p7-patch-live.json"))
    ap.add_argument("--probe", type=int, default=0, metavar="N",
                    help="skip the live target: generate N patches against "
                         "the degraded prompt and report how many APPLY")
    args = ap.parse_args()

    if args.probe:
        return probe(args.model, args.ollama, args.probe, args.json_out)

    settings = get_settings()
    client = TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config",
        admin_token=settings.target_admin_token,
    ))
    # The manifest lives in the TARGET repo, and the prompts directory is
    # whatever it declares - resolved the way `rca_f07_live.py` resolves it
    # rather than hard-coded here.
    target_path = Path(settings.target_path)
    manifest = load_manifest(target_path / "kavach.yaml")
    prompts_dir = (target_path / manifest.versioned_paths["prompts"]).resolve()

    out: dict[str, object] = {
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": args.model,
    }

    say("=" * 70)
    say("P7 LIVE - a generated patch, tried on a clone")
    say("=" * 70)

    if not sandbox.ollama_reachable():
        say("FAIL: ollama is not reachable")
        return 1

    good = (prompts_dir / PROMPT_FILE).read_text(encoding="utf-8")
    fault = F07PromptRegression(client, prompts_dir)

    try:
        say("\n[1/4] injecting F07 (degrading the target's answer.txt)")
        fault.inject()
        degraded = (prompts_dir / PROMPT_FILE).read_text(encoding="utf-8")
        say(f"      production answer.txt is now {len(degraded)} bytes")

        prod_fast = fast.run(client, FAST_SET, check_health=True)
        say(f"      production fast set: {prod_fast.pass_rate:.0%} "
            f"({'pass' if prod_fast.passed else 'FAIL, as intended'})")
        out["production_fast_rate_under_fault"] = prod_fast.pass_rate
        out["production_passed_under_fault"] = prod_fast.passed

        say("\n[2/4] asking the model for a patch")
        llm = OllamaClient(base_url=args.ollama, model=args.model)
        witness = {f"prompts/{PROMPT_FILE}": apply_patch.digest(degraded)}
        diagnosis = {
            "fault_class": "F07", "service": "backend", "confidence": 0.9,
            "reasoning": "the answer prompt no longer instructs grounding",
        }
        result = patch_engine.propose(
            llm=llm, diagnosis=diagnosis,
            evidence=("EV-C08 prompt answer.txt changed from the baseline; "
                      "grounding instructions are absent and answers no "
                      "longer cite the context"),
            target_path=f"prompts/{PROMPT_FILE}",
            file_contents=degraded,
            versioned_paths=manifest.versioned_paths,
            denied_mutations=manifest.denied_mutations,
            witness=witness,
            patch_root=prompts_dir.parent,
            boundary=prompts_dir.parent,
        )
        out["propose_latency_s"] = result.latency_s
        out["propose_usable"] = result.usable
        out["propose_reasons"] = result.reasons
        say(f"      usable={result.usable} in {result.latency_s}s")
        if result.proposal is not None:
            say(f"      rationale: {result.proposal.rationale[:120]}")
            out["diff"] = result.proposal.diff
        if not result.usable:
            say(f"      refused: {result.reasons or result.error}")
            out["verdict"] = "model produced no usable patch"
            return 1

        say("\n[3/4] building the action - this runs the SANDBOX trial")
        try:
            action = apply_patch.build_from_proposal(
                "INC-P7-LIVE", client, result, prompts_dir,
                manifest.versioned_paths,
                manifest.denied_mutations, witness,
            )
        except ActionError as exc:
            say(f"      the action was refused: {exc}")
            out["verdict"] = f"refused: {exc}"
            return 1

        say(f"      sandbox trial: {action.trial.detail}")
        out["sandbox_trial"] = action.trial.to_dict()
        out["risk_tier"] = action.risk_tier
        out["idempotency_key"] = action.idem_key

        say("\n[4/4] checking production was not touched")
        still = (prompts_dir / PROMPT_FILE).read_text(encoding="utf-8")
        untouched = still == degraded
        say(f"      production answer.txt unchanged by the trial: {untouched}")
        out["production_untouched"] = untouched
        out["executed"] = action.executed

        passed = bool(
            action.trial.passed and untouched and not action.executed
            and not prod_fast.passed
        )
        out["verdict"] = "PASS" if passed else "FAIL"
        say()
        say("=" * 70)
        say(f"  {out['verdict']}: the sandbox passed with a generated patch "
            f"while production stayed degraded" if passed else
            f"  {out['verdict']}")
        say("=" * 70)
        return 0 if passed else 1

    finally:
        fault.revert()
        back = (prompts_dir / PROMPT_FILE).read_text(encoding="utf-8")
        say(f"\nreverted: production answer.txt restored exactly: "
            f"{back == good}")
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(out, indent=2), encoding="utf-8", newline="")
        say(f"wrote {args.json_out}")


if __name__ == "__main__":
    raise SystemExit(main())
