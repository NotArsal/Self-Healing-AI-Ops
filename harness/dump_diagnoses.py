"""Freeze run B's diagnoses to an artifact before the ring buffer loses them.

`GET /v1/incidents` reads `runner`'s in-process ring, not Postgres
(`RESEARCH_NOTES.md` §7.2). The thirty-seven diagnoses behind §10 of the same
file - the `fault_name` incoherence, the `candidate_repair` gap, the second-draw
analysis - therefore exist only for as long as the API container stays up. One
`make down` and the evidence for a reported finding is gone.

So: write them down. Read-only, no injection, no gate interaction, nothing
mutated. Run while the API still holds the incidents:

    uv --directory apps/control-plane run python -I ../../harness/dump_diagnoses.py \
        --out ../../harness/reports/diagnoses-20261020.json

`--since` filters by `detected_at` so the aborted bench that preceded run B
(two incidents at 18:51-18:52) stays out of the sample.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Only the fields the findings rest on. `reasoning` and `raw_response` stay
# out: per `schemas.py`, raw generations do not belong in a committed artifact,
# and `reasoning` is up to 2000 characters of prose per row.
DIAG_FIELDS = (
    "fault_class", "fault_name", "service", "confidence",
    "candidate_repair", "evidence_ids",
)


def fetch(url: str, timeout: float) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--api", default="http://localhost:8080")
    p.add_argument("--out", required=True)
    p.add_argument("--since", default="", help="ISO prefix; keep detected_at >= this")
    p.add_argument("--timeout", type=float, default=20.0)
    a = p.parse_args()

    try:
        index = fetch(f"{a.api}/v1/incidents", a.timeout)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"the API is not answering at {a.api}: {exc}", file=sys.stderr)
        print("these rows live in memory only - nothing can recover them once "
              "the container has stopped.", file=sys.stderr)
        return 1

    rows = []
    for row in index:
        if a.since and str(row.get("detected_at", "")) < a.since:
            continue
        inc = fetch(f"{a.api}/v1/incidents/{row['incident_id']}", a.timeout)
        rca = inc.get("rca") or {}
        diag = rca.get("diagnosis") or {}
        det = inc.get("detection") or {}
        rows.append({
            "incident_id": inc["incident_id"],
            "detected_at": inc.get("detected_at", ""),
            "status": inc.get("status", ""),
            "escalation_reason": inc.get("escalation_reason") or "",
            "detection_class": det.get("fault_class") or "",
            "detection_concluded_at": det.get("concluded_at") or "",
            "model": rca.get("model") or "",
            "approved": rca.get("approved"),
            "approved_action": rca.get("approved_action"),
            "rejection_reasons": (rca.get("validation") or {}).get(
                "rejection_reasons") or [],
            "diagnosis": {k: diag.get(k) for k in DIAG_FIELDS} if diag else None,
        })

    rows.sort(key=lambda r: r["detected_at"])
    diagnosed = [r for r in rows if r["diagnosis"]]
    out = {
        "source": "GET /v1/incidents (in-process ring, see RESEARCH_NOTES 7.2)",
        "api": a.api,
        "since": a.since,
        "incidents": len(rows),
        "diagnoses": len(diagnosed),
        "rows": rows,
    }
    with Path(a.out).open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1, sort_keys=False)
        fh.write("\n")
    print(f"{len(rows)} incidents, {len(diagnosed)} diagnoses -> {a.out}")

    # The one assertion worth making here: a diagnosis whose own name does not
    # match its own class code is the finding this artifact exists to preserve.
    bad = [r for r in diagnosed
           if (r["diagnosis"]["fault_class"], r["diagnosis"]["fault_name"])
           not in CATALOGUE]
    print(f"  code/name pairs outside the catalogue: {len(bad)}/{len(diagnosed)}")
    return 0


# `llm/prompts/diagnose.txt`, the list the model is told to copy from.
CATALOGUE = {
    ("F01", "Primary LLM endpoint outage"),
    ("F02", "Primary LLM endpoint latency degradation"),
    ("F03", "Container crash-loop or out-of-memory"),
    ("F05", "Database connection pool exhaustion"),
    ("F06", "Retrieval collapse"),
    ("F07", "Prompt version regression"),
    ("F08", "Configuration or environment regression"),
    ("F09", "Token or cost blowout"),
}


if __name__ == "__main__":
    raise SystemExit(main())
