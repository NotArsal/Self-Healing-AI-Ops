"""Generation: what happens when the model answers, and when it misbehaves.

`test_patch_checks.py` proves the rules refuse bad patches. This proves the
rules are actually consulted, in the right order, and that nothing a model
can put in its reply lets it skip one.

The model is faked throughout. A real model's prose is measured live by a
harness; what is tested here is the machinery around it, which must behave
identically whatever the model says.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kavach.llm.client import LlmError, LlmResponse
from kavach.rca import patch_engine
from kavach.rca.patch_schema import ollama_schema

VERSIONED = {"prompts": "./prompts", "config": "runtime"}
DENIED = ["embed_model_change", "data_delete", "database_drop"]
WITNESS = {"prompts/answer.txt": "d55c73a23f33"}
DIAGNOSIS = {"fault_class": "F07", "service": "backend", "confidence": 0.9}


class FakeLlm:
    """Returns whatever reply the test wants, in the decoder's shape."""

    def __init__(self, reply: dict[str, Any] | str) -> None:
        self.reply = reply
        self.schema: dict[str, Any] | None = None

    def structured(self, system: str, user: str, schema: dict[str, Any],
                   temperature: float = 0.0) -> LlmResponse:
        self.schema = schema
        raw = self.reply if isinstance(self.reply, str) else json.dumps(self.reply)
        return LlmResponse(raw=raw, model="fake", latency_s=0.1,
                           prompt_tokens=1, completion_tokens=1)


@pytest.fixture
def area(tmp_path: Path) -> Path:
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "answer.txt").write_text("old line\n", encoding="utf-8", newline="")
    return tmp_path


def good_diff() -> str:
    return ("--- a/prompts/answer.txt\n+++ b/prompts/answer.txt\n"
            "@@ -1,1 +1,1 @@\n-old line\n+Answer only from the context.\n")


def run(llm: Any, area: Path, **over: Any) -> patch_engine.PatchResult:
    kwargs: dict[str, Any] = {
        "llm": llm, "diagnosis": DIAGNOSIS,
        "evidence": "EV-C08 prompt changed",
        "target_path": "prompts/answer.txt",
        "file_contents": "old line\n",
        "versioned_paths": VERSIONED, "denied_mutations": DENIED,
        "witness": WITNESS, "patch_root": area, "boundary": area,
    }
    kwargs.update(over)
    return patch_engine.propose(**kwargs)


# --- the decoder is constrained before the model speaks --------------------


def test_the_model_is_only_offered_the_declared_files(area: Path) -> None:
    """Refusing a bad answer and preventing one are different things, and
    this project already spent ten runs on a model inventing a value for a
    field whose valid set was in the prompt."""
    llm = FakeLlm({"target_path": "prompts/answer.txt",
                   "rationale": "restore grounding", "diff": good_diff()})
    run(llm, area)
    assert llm.schema is not None
    assert llm.schema["properties"]["target_path"]["enum"] == [
        "prompts/answer.txt"
    ]


def test_a_schema_with_nowhere_to_write_is_refused_not_permissive() -> None:
    with pytest.raises(ValueError, match="nothing a patch could target"):
        ollama_schema([])


# --- the happy path, and it is still not permission to write ---------------


def test_a_good_patch_is_usable_but_its_sandbox_result_is_still_unknown(
    area: Path,
) -> None:
    llm = FakeLlm({"target_path": "prompts/answer.txt",
                   "rationale": "restore the grounding instruction",
                   "diff": good_diff()})
    r = run(llm, area)
    assert r.usable, r.reasons
    assert r.applies_cleanly
    assert r.proposal is not None
    # The decisive part: `usable` means "worth trying in a sandbox", never
    # "safe for production". Running the FULL six-check gate on the same
    # patch, with no sandbox result, still refuses it.
    from kavach.executor import patch_checks
    final = patch_checks.evaluate(
        r.proposal.diff, VERSIONED, DENIED, WITNESS, sandbox_passed=None)
    assert not final.allowed
    assert any("no sandbox result" in x for x in final.reasons)


# --- a model that misbehaves ----------------------------------------------


def test_a_patch_outside_the_declared_paths_is_refused(area: Path) -> None:
    bad = ("--- a/backend/db.py\n+++ b/backend/db.py\n"
           "@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n")
    r = run(FakeLlm({"target_path": "prompts/answer.txt",
                     "rationale": "fix", "diff": bad}), area)
    assert not r.usable
    assert any("not under any declared versioned path" in x for x in r.reasons)


def test_a_patch_adding_denied_content_is_refused(area: Path) -> None:
    bad = ("--- a/prompts/answer.txt\n+++ b/prompts/answer.txt\n"
           "@@ -1,1 +1,1 @@\n-old line\n+Then run DROP TABLE document_chunks;\n")
    r = run(FakeLlm({"target_path": "prompts/answer.txt",
                     "rationale": "fix", "diff": bad}), area)
    assert not r.usable
    assert any("deny-list refuses on content" in x for x in r.reasons)


def test_a_whole_file_instead_of_a_diff_is_refused(area: Path) -> None:
    r = run(FakeLlm({"target_path": "prompts/answer.txt", "rationale": "fix",
                     "diff": "You are a helpful assistant.\n{context}\n"}),
            area)
    assert not r.usable
    assert any("not a unified diff" in x for x in r.reasons)


def test_a_path_outside_the_enum_is_called_out_specifically(
    area: Path,
) -> None:
    """If the model returns a value the decoder was told to forbid, the
    constraint did not hold - which is worse news than a refused patch and
    should not be folded into a generic path error."""
    r = run(FakeLlm({"target_path": "prompts/invented.txt",
                     "rationale": "fix", "diff": good_diff()}), area)
    assert not r.usable
    assert any("decoder constraint did not hold" in x for x in r.reasons)


def test_a_patch_that_no_longer_fits_the_file_is_refused(area: Path) -> None:
    """Permitted and applicable are different questions. This patch breaks
    no rule; the file simply moved underneath it."""
    (area / "prompts" / "answer.txt").write_text(
        "a human rewrote this\n", encoding="utf-8", newline="")
    r = run(FakeLlm({"target_path": "prompts/answer.txt",
                     "rationale": "fix", "diff": good_diff()}), area)
    assert not r.usable
    assert r.applies_cleanly is False
    assert any("does not apply to the file as it stands" in x
               for x in r.reasons)
    assert (area / "prompts" / "answer.txt").read_text(encoding="utf-8") == (
        "a human rewrote this\n"
    ), "the human's edit was overwritten"


# --- the model failing, rather than misbehaving ----------------------------


def test_a_model_that_returns_nonsense_is_an_error_not_a_crash(
    area: Path,
) -> None:
    r = run(FakeLlm("not json at all"), area)
    assert not r.usable
    assert r.error
    assert r.proposal is None


def test_a_model_that_is_unreachable_is_an_error_not_a_crash(
    area: Path,
) -> None:
    class Dead:
        def structured(self, **kw: Any) -> LlmResponse:
            raise LlmError("connection refused")

    r = run(Dead(), area)
    assert not r.usable
    assert "connection refused" in r.error


# --- nothing is written by proposing --------------------------------------


def test_proposing_writes_nothing_whatever_the_model_says(area: Path) -> None:
    before = (area / "prompts" / "answer.txt").read_text(encoding="utf-8")
    run(FakeLlm({"target_path": "prompts/answer.txt", "rationale": "fix",
                 "diff": good_diff()}), area)
    assert (area / "prompts" / "answer.txt").read_text(encoding="utf-8") == (
        before
    ), "propose() wrote to a file; it may only ever return a proposal"
