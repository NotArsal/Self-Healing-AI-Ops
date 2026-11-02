"""The RCA model default must be the same in all three places that state it.

THE BUG THIS PINS, found 2026-11-03 by making the mistake.

Three places declare a default RCA model, and they disagreed:

    ARCHITECTURE.md §2.4      qwen2.5:7b-instruct   (the documented default)
    kavach/config.py          llama3.2
    infra/docker-compose.yml  llama3.2

`.env` sets the correct value, so the stack was right whenever it was started
through `make up`, which passes `--env-file .env`. A bare `docker compose up`
does not pass it, takes the compose fallback, and silently installs a model
that cannot diagnose two of the four fault classes. Measured on this
repository's own ablation artifacts:

    llama3.2              F01 10/10   F07  0/10   F08  0/10
    qwen2.5:7b-instruct   F01 10/10   F07 10/10   F08 10/10

Every F07 and F08 diagnosis under llama3.2 collapses to F06. A rehearsal
started that way reported `RCA model llama3.2` and would have failed two acts
for a reason that looks like a model defect rather than a missing env file.

This is the same defect class as the corpus fingerprint and the drain
threshold: two components stating the same fact by different values, where the
wrong one is silently survivable.
"""

from __future__ import annotations

import re
from pathlib import Path

from kavach.config import Settings

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "infra" / "docker-compose.yml"
ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"

# Not a constant to compare against - the point is that the three SOURCES
# agree with each other. This only names what they currently agree on, so a
# deliberate change has to be made in all three and here, which is the
# review gate.
EXPECTED = "qwen2.5:7b-instruct"


def test_the_settings_default_is_the_documented_default() -> None:
    assert Settings(llm_model=EXPECTED).llm_model == EXPECTED
    # The unset default, which is what a process with no env file gets.
    assert Settings().llm_model == EXPECTED, (
        "kavach/config.py's llm_model default disagrees with ARCHITECTURE.md "
        "§2.4. If the code default is a model that scores 0/10 on F07 and "
        "F08, any process started without an env file silently loses two "
        "fault classes.")


def test_the_compose_fallback_is_the_documented_default() -> None:
    """`make up` passes --env-file, a bare `docker compose up` does not."""
    text = COMPOSE.read_text(encoding="utf-8")
    found = re.search(r"KAVACH_LLM_MODEL:\s*\$\{KAVACH_LLM_MODEL:-([^}]*)\}",
                      text)
    assert found, "the compose file no longer declares a KAVACH_LLM_MODEL fallback"
    assert found.group(1).strip() == EXPECTED, (
        f"infra/docker-compose.yml falls back to {found.group(1)!r}. A bare "
        f"`docker compose up` takes this path, so it must not be a model that "
        f"cannot diagnose F07 or F08.")


def test_the_architecture_document_still_names_this_default() -> None:
    """If the documented default changes, this test should fail and force the
    other two to be changed with it rather than drifting apart again."""
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert re.search(rf"KAVACH_LLM_MODEL`?,?\s*default\s*`?{re.escape(EXPECTED)}",
                     text), (
        f"ARCHITECTURE.md no longer documents {EXPECTED!r} as the RCA model "
        f"default. Update config.py, docker-compose.yml and this test "
        f"together - the three drifting apart is the bug this file exists for.")


def test_the_measured_difference_is_still_in_the_artifacts() -> None:
    """The justification, not just the assertion.

    Reads the committed ablation artifacts rather than restating their
    numbers, so this test fails if the evidence for preferring qwen ever stops
    existing - at which point the default is a preference again and should be
    argued rather than asserted.
    """
    import json

    reports = ROOT / "harness" / "reports"
    collapsed: dict[str, str] = {}
    for name in ("p6-f07-rca.json", "p6-f08-rca.json"):
        path = reports / name
        if not path.is_file():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        if "llama" not in str(doc.get("model", "")):
            continue
        classes = {r.get("fault_class") for r in doc.get("runs", [])}
        collapsed[name] = ",".join(sorted(str(c) for c in classes))

    assert collapsed, (
        "no llama3.2 ablation artifact found under harness/reports; the "
        "measured case for the default has gone missing")
    # `seen` and not `classes`: the name above is bound to a set in the loop
    # that builds this dict, and reusing it here made mypy compare a set
    # against a string - a real type confusion, caught by --strict.
    for name, seen in collapsed.items():
        assert seen == "F06", (
            f"{name} no longer shows llama3.2 collapsing to F06 (saw "
            f"{seen}). Re-check whether the default is still justified.")
