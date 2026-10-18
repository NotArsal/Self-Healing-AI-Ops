"""The postmortem Kavach writes about itself.

A renderer, not a collector. Every fact below is already recorded by the
time an incident ends - the evidence frame, the `permit()` decision, the
action and its inverse, the fast set before and after, and the audit
chain's own verification. Nothing here reaches for the target, calls a
model, or computes a number that is not already written down. If a figure
is missing from the record it is reported as missing rather than
recalculated, because a postmortem that quietly recomputes its evidence is
a second opinion rather than an account.

WHY THIS EXISTS
The audit log is a hash-chained JSONL file. It is exactly right for proving
nothing was altered and exactly wrong for reading, and "the audit trail is
real" is a claim nobody checks by scrolling JSON. A survey of AI SRE
tooling in 2026 put it bluntly: postmortems are the low-hanging fruit
almost nobody has picked. See `docs/RESEARCH_NOTES.md` §3.1.

IT REPORTS FAILURES AS READILY AS SUCCESSES
An incident that was denied, escalated, refused by the sandbox or unwound
gets the same treatment as one that healed. That is the point. A tool that
only writes up its wins is marketing, and the refusals are where this
project's argument actually lives - a patch that passed all six checks and
still failed in the sandbox is the most informative thing it has produced.

THE CHAIN IS VERIFIED HERE, NOT ASSUMED
`verify()` runs when the log is supplied, and its answer goes in the
document whichever way it comes out. A postmortem that asserts integrity
without checking would be worse than one that omits the claim.
"""

from __future__ import annotations

import contextlib
from datetime import datetime
from pathlib import Path
from typing import Any

from kavach.audit.log import AuditLog

# Stages in the order they happen, with the audit event that marks each.
# Rows carry whatever the loop passed, so the renderer names the stage and
# shows the fields rather than assuming a shape.
STAGE_ORDER = ("detect", "diagnose", "gate", "execute", "verify", "unwind")


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return f"{value:.3g}"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _elapsed(start: str, end: str) -> str:
    """Wall time between two ISO stamps, or an em dash if either is absent."""
    if not start or not end:
        return "—"
    try:
        a = datetime.fromisoformat(start)
        b = datetime.fromisoformat(end)
    except ValueError:
        return "—"
    return f"{(b - a).total_seconds():.1f}s"


def _fast(block: dict[str, Any]) -> str:
    if not block:
        return "—"
    rate = block.get("pass_rate")
    passed = block.get("passed")
    if rate is None:
        return "—"
    return f"{float(rate):.0%} ({'pass' if passed else 'fail'})"


def render(
    incident: Any,
    audit: AuditLog | None = None,
    evidence: str = "",
) -> str:
    """One Markdown postmortem for one incident.

    `incident` is duck-typed rather than imported, because `loop.py` imports
    this module's package and a renderer that forced the dependency the
    other way would be a cycle for no benefit.
    """
    d = incident.to_dict() if hasattr(incident, "to_dict") else dict(incident)
    iid = str(d.get("incident_id", "unknown"))
    rows = [r for r in (audit.rows() if audit else [])
            if r.get("incident_id") == iid]

    out: list[str] = []
    add = out.append

    status = str(d.get("status", "unknown"))
    add(f"# Incident {iid} — {status}")
    add("")
    add(f"*{d.get('project', 'unknown project')}, "
        f"detected {_fmt(d.get('detected_at'))}*")
    add("")

    # --- the one-paragraph version -----------------------------------------
    add("## What happened")
    add("")
    add(str(d.get("outcome") or "No outcome was recorded."))
    if d.get("escalation_reason"):
        add("")
        add(f"**Escalated:** {d['escalation_reason']}")
    add("")

    # --- the timeline -------------------------------------------------------
    add("## Timeline")
    add("")
    add("| stage | at | detail |")
    add("|---|---|---|")
    if rows:
        for r in rows:
            detail = r.get("detail") or r.get("verdict") or r.get("status") or ""
            add(f"| {_fmt(r.get('event'))} | {_fmt(r.get('at'))} | "
                f"{_fmt(detail)[:90]} |")
    else:
        add("| — | — | no audit rows for this incident |")
    add("")
    add(f"**Detected to resolved:** "
        f"{_elapsed(str(d.get('detected_at', '')), str(d.get('resolved_at', '')))}")
    add("")

    # --- what the evidence said --------------------------------------------
    add("## What the evidence said")
    add("")
    det = d.get("detection") or {}
    verdict_line = f"- Detector verdict: **{_fmt(det.get('verdict'))}**"
    if det.get("detail"):
        verdict_line += f" — {det['detail']}"
    add(verdict_line)
    add(f"- Fault class: **{_fmt(d.get('fault_class'))}** "
        f"on **{_fmt(d.get('service'))}**")
    add(f"- Diagnosed by: **{_fmt(d.get('diagnosed_by'))}**")

    rca = d.get("rca") or {}
    if rca:
        # The model's OWN answer lives under `diagnosis`. Reading
        # `incident.fault_class` here instead would print the deterministic
        # verdict, which is present in both arms and once flattered the
        # model into a perfect score - the same mistake `report.py` carries
        # a warning about.
        dg = rca.get("diagnosis") or {}
        add(f"- Model ({_fmt(rca.get('model'))}): "
            f"**{_fmt(dg.get('fault_class'))}** at confidence "
            f"{_fmt(dg.get('confidence'))}, citing "
            f"{_fmt(', '.join(dg.get('evidence_ids') or []))}")
        agrees = dg.get("fault_class") == d.get("fault_class")
        add(f"- Agrees with the deterministic detector: "
            f"**{'yes' if agrees else 'NO'}**")
        add(f"- Validator accepted: **{_fmt(rca.get('approved'))}**"
            + (f" — {rca['error']}" if rca.get("error") else ""))
        if dg.get("reasoning"):
            add("")
            add(f"> {str(dg['reasoning'])[:600]}")
    if evidence:
        add("")
        add("<details><summary>Evidence frame as the model saw it</summary>")
        add("")
        add("```")
        add(evidence.strip()[:4000])
        add("```")
        add("")
        add("</details>")
    add("")

    # --- what the gate decided ----------------------------------------------
    add("## What the gate decided")
    add("")
    dec = d.get("decision") or {}
    if dec:
        add(f"- Verdict: **{_fmt(dec.get('verdict'))}** "
            f"(risk {_fmt(dec.get('risk_tier'))}, mode {_fmt(dec.get('mode'))})")
        for reason in (dec.get("reasons") or []):
            add(f"  - {reason}")
    else:
        add("- No `permit()` decision was recorded; nothing reached the gate.")
    add("")

    # --- what was written, and what undoes it -------------------------------
    add("## What was written")
    add("")
    act = d.get("action") or {}
    if act:
        add(f"- Action: **{_fmt(d.get('planned_action'))}** "
            f"(risk {_fmt(act.get('risk_tier'))})")
        add(f"- Requested: `{_fmt(act.get('requested_settings'))}`")
        # The inverse is printed whether or not it ran. An action whose undo
        # exists but was never needed is the normal case, and showing it is
        # how a reader checks the recoverability claim without taking it on
        # trust.
        add(f"- Inverse held: `{_fmt(act.get('inverse_settings'))}`")
        add(f"- Executed: **{_fmt(act.get('executed'))}**, "
            f"reverted: **{_fmt(act.get('reverted'))}**")
        if act.get("sandbox_trial"):
            t = act["sandbox_trial"]
            add(f"- Sandbox trial: **{_fmt(t.get('detail'))}**")
        if act.get("diff"):
            add("")
            add("<details><summary>The patch, as the model wrote it</summary>")
            add("")
            add("```diff")
            add(str(act["diff"]).strip()[:4000])
            add("```")
            add("")
            add("</details>")
    else:
        add("- Nothing was written.")
    add("")

    # --- did it work --------------------------------------------------------
    add("## Did it work")
    add("")
    # `verification` IS the post-repair fast set, not a before/after pair;
    # the pre-repair reading is what the detector saw.
    ver = d.get("verification") or {}
    det_fast = (d.get("detection") or {}).get("pre_verification") or {}
    before_block = det_fast or ver.get("before") or {}
    add(f"- Fast set before: **{_fast(before_block)}**")
    add(f"- Fast set after: **{_fast(ver if 'pass_rate' in ver else (ver.get('after') or {}))}**")
    if ver.get("total_s") is not None:
        add(f"- Verification took {_fmt(ver.get('total_s'))}s against a "
            f"{_fmt(ver.get('budget_s'))}s budget")
    if d.get("unwind"):
        add(f"- Unwind: {_fmt(d['unwind'].get('detail') or d['unwind'])}")
    before = d.get("corpus_before") or {}
    after = d.get("corpus_after") or {}
    if before or after:
        same = before == after
        add(f"- Corpus unchanged: **{'yes' if same else 'NO'}** "
            f"({_fmt(before.get('chunks'))} → {_fmt(after.get('chunks'))} chunks)")
    add("")

    # --- the chain ----------------------------------------------------------
    add("## Audit chain")
    add("")
    if audit is None:
        add("- No audit log was supplied, so integrity is **not claimed** here.")
    else:
        check = audit.verify()
        add(f"- Rows for this incident: {len(rows)} of {check.rows} in the log")
        add(f"- Hash chain intact: **{'yes' if check.intact else 'NO'}**")
        if not check.intact:
            add(f"- First break at row {check.broken_at}: {check.detail}")
        if check.malformed:
            add(f"- Malformed rows: {check.malformed}")
    add("")
    add("---")
    add("")
    add("*Written by Kavach from its own audit record. Every figure above was "
        "recorded during the incident; none was recomputed afterwards.*")
    return "\n".join(out)


def _main() -> int:
    """`python -m kavach.audit.postmortem` — render one incident.

    Reads the running control plane rather than a file, because the
    incident record lives in the API and the audit log lives inside its
    container. With no id, the most recent incident is used, which is what
    you want immediately after a demo run.
    """
    import argparse
    import json
    import urllib.request

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("incident_id", nargs="?", default="",
                    help="default: the most recent incident")
    ap.add_argument("--api", default="http://127.0.0.1:8080/v1",
                    help="the control plane, including its /v1 prefix")
    ap.add_argument("--out", default="", help="default: stdout")
    args = ap.parse_args()

    def get(path: str) -> Any:
        with urllib.request.urlopen(f"{args.api}{path}", timeout=30) as r:
            return json.load(r)

    try:
        iid = args.incident_id
        if not iid:
            listing = get("/incidents")
            if not listing:
                print("no incidents recorded yet")
                return 1
            iid = listing[0].get("incident_id") or listing[-1].get("incident_id")
        incident = get(f"/incidents/{iid}")
    except Exception as exc:
        print(f"could not read {args.api}: {exc}")
        return 1

    # The audit log is read through the API too. It lives inside the
    # container, and a renderer that needed a bind mount would work on the
    # developer's machine and nowhere else.
    rows: list[dict[str, Any]] = []
    with contextlib.suppress(Exception):
        rows = list(get("/audit").get("rows") or [])

    text = render(incident, audit=None)
    if rows:
        mine = [r for r in rows if r.get("incident_id") == iid]
        timeline = ["| stage | at | detail |", "|---|---|---|"]
        for r in mine:
            detail = r.get("detail") or r.get("verdict") or r.get("status") or ""
            timeline.append(f"| {_fmt(r.get('event'))} | {_fmt(r.get('at'))} "
                            f"| {_fmt(detail)[:90]} |")
        text = text.replace(
            "| — | — | no audit rows for this incident |",
            "\n".join(timeline[2:]) or "| — | — | none |")

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
