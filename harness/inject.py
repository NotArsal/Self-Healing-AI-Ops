"""`inject.py` — the fault-injection CLI, justified at last by a second fault.

`ROADMAP.md` P2 deliberately skipped this: one injector with one caller did not
need a command-line front end, and building one then would have been an
abstraction over a single case. P6 adds `F01`, so there are now two injectors
with the same shape, and the registry below is the thing that keeps a third
from being a third special case.

WHAT IT IS FOR
Driving a fault by hand - on stage, or while debugging - without writing a
throwaway script that forgets to revert. Every subcommand that injects also
knows how to put the target back, and `revert` is safe to run when nothing is
injected.

WHAT IT IS NOT
It does not heal anything, and it never touches Kavach. Injecting is the
experiment's setup; detection, diagnosis and repair are what is being measured
and they go through the control plane. A CLI that could also repair would make
it possible to demonstrate a heal that never happened.

    uv run --project apps/control-plane python -I harness/inject.py list
    uv run --project apps/control-plane python -I harness/inject.py status
    uv run --project apps/control-plane python -I harness/inject.py inject F01
    uv run --project apps/control-plane python -I harness/inject.py revert F01
    uv run --project apps/control-plane python -I harness/inject.py revert --all

`KAVACH_TARGET_ADMIN_TOKEN` must be set for anything that writes config.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps" / "control-plane")]

from harness.faults.base import Fault  # noqa: E402
from harness.faults.f01_endpoint_outage import F01EndpointOutage  # noqa: E402
from harness.faults.f06_retrieval_collapse import F06RetrievalCollapse  # noqa: E402
from harness.faults.f07_prompt_regression import F07PromptRegression  # noqa: E402
from harness.faults.f08_config_regression import F08ConfigRegression  # noqa: E402
from kavach.target import TargetClient, TargetEndpoints  # noqa: E402

TARGET = "http://127.0.0.1:8000"
DEFAULT_PROM = "http://127.0.0.1:9091"


def say(m: str = "") -> None:
    print(m, flush=True)


def promql(prometheus_url: str, query: str) -> float | None:
    url = prometheus_url + "/api/v1/query?query=" + urllib.parse.quote(query)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            res = json.loads(r.read())["data"]["result"]
        return float(res[0]["value"][1]) if res else None
    except Exception:
        return None


# Name -> how to build its injector. The ONE place a fault class is wired to
# this CLI, so adding the next one is a line here rather than a new branch in
# every subcommand.
Builder = Callable[[TargetClient, Callable[[], dict[str, Any]]], Fault]

def prompts_dir() -> Path:
    """Where the target keeps its prompts, as the target itself declares it.

    Resolved from the manifest rather than hardcoded, for the reason the
    executor resolves the backup endpoint from the manifest: a path to a
    workload's files, written into the control plane, is the control plane
    knowing a workload's layout.
    """
    from kavach.config import get_settings
    from kavach.onboarding.manifest import load

    target = Path(get_settings().target_path)
    declared = load(target / "kavach.yaml").versioned_paths.get("prompts")
    if not declared:
        raise SystemExit(
            "the target manifest declares no `versioned_paths.prompts`, so "
            "there is nowhere to inject a prompt regression"
        )
    return (target / declared).resolve()


FAULTS: dict[str, Builder] = {
    # F01 drives Toxiproxy's admin API, not the target, so it takes no client.
    "F01": lambda _client, corpus: F01EndpointOutage(corpus_probe=corpus),
    "F06": lambda client, corpus: F06RetrievalCollapse(client, corpus_probe=corpus),
    # F07 writes a FILE rather than a setting, so it needs the prompts
    # directory as well as the control interface - it uses the first to inject
    # and the second to confirm the running target actually saw it.
    "F07": lambda client, corpus: F07PromptRegression(
        client, prompts_dir(), corpus_probe=corpus),
    "F08": lambda client, corpus: F08ConfigRegression(client, corpus_probe=corpus),
}


def build(name: str, client: TargetClient, prometheus_url: str) -> Fault:
    key = name.upper()
    if key not in FAULTS:
        raise SystemExit(
            f"unknown fault {name!r}. Known: {', '.join(sorted(FAULTS))}. "
            f"The catalogue's other classes have no injector yet, and a "
            f"placeholder injector would corrupt every number derived from it "
            f"(AGENTS.md)."
        )

    def corpus() -> dict[str, Any]:
        return {"chunks": promql(prometheus_url, "ragapp_corpus_chunks"),
                "files": promql(prometheus_url, "ragapp_corpus_files")}

    return FAULTS[key](client, corpus)


def client_for(admin_token: str) -> TargetClient:
    return TargetClient(TargetEndpoints(
        health=TARGET + "/healthz", chat=TARGET + "/v1/chat",
        config=TARGET + "/v1/admin/config", admin_token=admin_token))


def cmd_list() -> int:
    say("fault classes with a real injector:")
    for name in sorted(FAULTS):
        say(f"  {name}")
    say("")
    say("Everything else in the catalogue is deliberately absent: a placeholder")
    say("injector would make every number derived from it meaningless.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    client = client_for(args.admin_token)
    say("target:")
    try:
        settings = client.settings()
        say(f"  rerank_threshold   {settings.get('rerank_threshold')}")
        say(f"  llm_base_url       {settings.get('llm_base_url')}")
        say(f"  config_hash        {client.config_hash()}")
    except Exception as exc:
        say(f"  unreachable: {exc}")
        return 1
    say(f"  corpus             chunks="
        f"{promql(args.prometheus, 'ragapp_corpus_chunks')} "
        f"files={promql(args.prometheus, 'ragapp_corpus_files')}")
    say("")
    say("injected right now:")
    any_active = False
    for name in sorted(FAULTS):
        try:
            active = build(name, client, args.prometheus).is_active()
        except Exception as exc:
            say(f"  {name}  unknown ({type(exc).__name__})")
            continue
        if active:
            any_active = True
        say(f"  {name}  {'ACTIVE' if active else 'clear'}")
    if any_active:
        say("")
        say("  Something is injected. `revert --all` puts the target back.")
    return 0


def cmd_inject(args: argparse.Namespace) -> int:
    client = client_for(args.admin_token)
    fault = build(args.fault, client, args.prometheus)
    if fault.is_active():
        say(f"{args.fault.upper()} is already injected; nothing to do. "
            f"Revert it first if you want a fresh pre-state.")
        return 1
    record = fault.inject()
    say(f"injected {fault.fault_class} {fault.fault_name} on {fault.service}")
    say(f"  applied   {record.applied}")
    say(f"  pre-state {json.dumps(record.pre_state, default=str)[:300]}")
    say("")
    say("THE PRE-STATE ABOVE LIVES ONLY IN THIS PROCESS, WHICH IS NOW EXITING.")
    say(f"`revert {fault.fault_class}` re-reads the live state and undoes the")
    say("known change, which is correct for these two faults but is NOT a")
    say("replay of the witness. For a measured run use the harnesses, which")
    say("hold the record and revert in a finally block.")
    return 0


def cmd_revert(args: argparse.Namespace) -> int:
    client = client_for(args.admin_token)
    names = sorted(FAULTS) if args.all else [args.fault]
    worst = 0
    for name in names:
        fault = build(name, client, args.prometheus)
        try:
            if not fault.is_active():
                say(f"{name}  clear already")
                continue
            # A fresh process has no captured pre-state, so `revert()` would
            # return without doing anything. Undo the known change instead,
            # and say so rather than pretending a witness was replayed.
            fault.record.pre_state = _assumed_pre_state(name, fault)
            fault.revert()
            say(f"{name}  reverted -> {_describe(name, fault)}")
        except Exception as exc:
            say(f"{name}  FAILED: {type(exc).__name__}: {exc}")
            worst = 1
    return worst


def _assumed_pre_state(name: str, fault: Fault) -> dict[str, Any]:
    """The healthy value for a fault injected by a process that has exited.

    Stated as an assumption, not disguised as a witness. Each entry is the
    documented healthy value from the injector's own module, and `revert`
    prints what it restored so a wrong assumption is visible rather than
    silent.
    """
    if name == "F01":
        from harness.faults.f01_endpoint_outage import PRIMARY

        proxy = fault._proxy(PRIMARY)  # type: ignore[attr-defined]
        return {"proxy": {**proxy, "enabled": True}}
    if name == "F06":
        from harness.faults.f06_retrieval_collapse import (
            EXPECTED_HEALTHY_THRESHOLD,
            SETTING,
        )

        return {"settings": {SETTING: EXPECTED_HEALTHY_THRESHOLD}}
    if name == "F08":
        from harness.faults.f08_config_regression import (
            EXPECTED_HEALTHY_MAX_TOKENS,
        )
        from harness.faults.f08_config_regression import (
            SETTING as F08_SETTING,
        )

        return {"settings": {F08_SETTING: EXPECTED_HEALTHY_MAX_TOKENS}}
    if name == "F07":
        # Deliberately refused rather than answered. Every other fault here
        # has a documented healthy CONSTANT; F07's healthy state is the text
        # of a file, which is recorded in the baseline capture and nowhere
        # else. Inventing one would write a prompt nobody ever ran.
        raise SystemExit(
            "F07 has no documented healthy constant: the known-good prompt is "
            "the text `make onboard` captured, not a value that can be stated "
            "here. Revert it in the process that injected it, or restore "
            "`prompt_contents` from the newest baseline under harness/baselines/"
        )
    raise SystemExit(f"no documented healthy state for {name}")


def _describe(name: str, fault: Fault) -> str:
    try:
        if name == "F01":
            from harness.faults.f01_endpoint_outage import PRIMARY

            enabled = fault._proxy(PRIMARY).get("enabled")  # type: ignore[attr-defined]
            return f"{PRIMARY} enabled={enabled}"
        if name == "F06":
            return f"rerank_threshold={fault.current_threshold()}"  # type: ignore[attr-defined]
        if name == "F07":
            from harness.faults.f07_prompt_regression import PROMPT_FILE

            live = fault.reported_digests().get(PROMPT_FILE)  # type: ignore[attr-defined]
            return f"{PROMPT_FILE} digest={live} (as the TARGET reports it)"
        if name == "F08":
            return f"max_tokens={fault.current_max_tokens()}"  # type: ignore[attr-defined]
    except Exception as exc:
        return f"(could not read back: {exc})"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    ap.add_argument("--prometheus", default=DEFAULT_PROM)
    ap.add_argument("--admin-token",
                    default=os.environ.get("KAVACH_TARGET_ADMIN_TOKEN", ""))
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="fault classes with a real injector")
    sub.add_parser("status", help="target state, and what is injected")

    p_inject = sub.add_parser("inject", help="apply a fault")
    p_inject.add_argument("fault")

    p_revert = sub.add_parser("revert", help="undo a fault")
    p_revert.add_argument("fault", nargs="?", default="")
    p_revert.add_argument("--all", action="store_true",
                          help="revert every known fault class")

    args = ap.parse_args()
    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "inject":
        return cmd_inject(args)
    if args.cmd == "revert":
        if not args.fault and not args.all:
            ap.error("revert needs a fault class or --all")
        return cmd_revert(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
