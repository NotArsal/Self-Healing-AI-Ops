"""Does the target still answer correctly on a larger corpus? Ground truth from the books.

Part of the larger-corpus experiment (docs/EXPERIMENT_LARGER_CORPUS.md). Each
question's expected fact was copied from the book's own extracted text on
2026-11-19, so a pass means the target retrieved and used that passage. A
case passes only if the answer is not a refusal, contains the fact, and
cites the right file. The LSTM case is the control: it must still come from
the original corpus.

    uv --directory apps/control-plane run python -I ../../harness/corpus_answers.py --out FILE
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

CHAT = "http://127.0.0.1:8000/v1/chat"
SWE, BEL, ORIG = "swe_at_google.pdf", "belonging_sonia_gandhi.pdf", "1662.pdf"

# (question, any of these facts, the file it must cite)
CASES: list[tuple[str, tuple[str, ...], str]] = [
    ("How does the Software Engineering at Google book define software engineering?",
     ("integrated over time",), SWE),
    ("What is Hyrum's Law?", ("observable behavior",), SWE),
    ("What is the Beyoncé Rule at Google?", ("CI test",), SWE),
    ("What is the Beyonce Rule at Google?", ("CI test",), SWE),      # no accent
    ("What does TAP stand for in Google's CI system?", ("Platform",), SWE),
    ("What does LGTM mean in Google code review?", ("looks good to me",), SWE),
    ("What is the name of Google's centralized version control system?", ("Piper",), SWE),
    ("In which town did Sonia Gandhi's family live in Italy?", ("Orbassano",), BEL),
    ("What were the names of Sonia Gandhi's parents?", ("Stefano",), BEL),
    ("What was the Varsity in Cambridge?", ("Greek",), BEL),
    ("Where did Sonia Gandhi meet Rajiv Gandhi?", ("Cambridge", "Varsity"), BEL),
    ("Which province is Orbassano in?", ("Torino", "Turin"), BEL),
    ("What ROC-AUC did the LSTM model achieve?", ("0.91",), ORIG),   # control
]
REFUSAL = re.compile(r"I don.t know", re.I)


def ask(question: str) -> tuple[str, float]:
    req = urllib.request.Request(CHAT, data=json.dumps({"question": question}).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as r:
        answer = str(json.load(r).get("answer") or "")
    return answer, round(time.perf_counter() - t0, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows: list[dict[str, Any]] = []
    for question, facts, source in CASES:
        answer, seconds = ask(question)
        body, _, sources = answer.partition("**Sources:**")
        cited = sorted(set(re.findall(r"`([^`]+\.pdf)`", sources)))
        row: dict[str, Any] = {
            "question": question, "expected_source": source, "cited": cited,
            "answered": not REFUSAL.search(body),
            "fact_present": any(f.lower() in body.lower() for f in facts),
            "right_source": source in cited, "latency_s": seconds,
            "answer": " ".join(body.split())[:300],
        }
        row["passed"] = row["answered"] and row["fact_present"] and row["right_source"]
        rows.append(row)
        print(f"{'PASS' if row['passed'] else 'FAIL'}  {seconds:5.1f}s  {question[:58]:58}  "
              f"cited={','.join(cited) or '-'}", flush=True)
    passed = sum(r["passed"] for r in rows)
    print(f"\n{passed}/{len(rows)} passed")
    Path(args.out).write_text(json.dumps({"cases": rows, "passed": passed,
                                          "total": len(rows)}, indent=2) + "\n",
                              encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
