"""The six checks that stand between a model's output and a file.

`apply_patch` is the one action where the model supplies CONTENT rather than
picking a name, and `PRD.md` §12 calls it "the highest-risk thing in the
system". The safety argument is that the decision stays deterministic even
though the payload is generated, so these tests are written the only way
that argument can be tested: one per constraint, each trying to get a
forbidden patch past it.

A patch that should be allowed has exactly one test. Patches that must be
refused have most of the file. That ratio is deliberate.
"""

from __future__ import annotations

import pytest

from kavach.executor import patch_checks as pc

VERSIONED = {"prompts": "./prompts", "config": "runtime"}
DENIED = ["embed_model_change", "data_delete", "database_drop",
          "scale_to_zero", "migration"]
WITNESS = {"prompts/answer.txt": "d55c73a23f33",
           "prompts/query_expansion.txt": "bbc6a7fee760"}


def diff(path: str = "prompts/answer.txt", added: list[str] | None = None,
         removed: list[str] | None = None) -> str:
    """A minimal well-formed unified diff."""
    body = "".join(f"-{ln}\n" for ln in (removed or ["old line"]))
    body += "".join(f"+{ln}\n" for ln in (added or ["new line"]))
    return (f"--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,1 @@\n{body}")


# --- the one that must be allowed ------------------------------------------


def test_a_small_prompt_patch_that_passed_the_sandbox_is_allowed() -> None:
    v = pc.evaluate(diff(added=["Answer using only the context provided."]),
                    VERSIONED, DENIED, WITNESS, sandbox_passed=True)
    assert v.allowed, v.reasons
    assert v.files == ["prompts/answer.txt"]


# --- constraint 4: sandbox mandatory, not routed ---------------------------


def test_no_sandbox_result_is_a_refusal_not_a_default() -> None:
    """`None` is the dangerous value: it means nobody checked, which must
    never read the same as 'checked and fine'."""
    v = pc.evaluate(diff(), VERSIONED, DENIED, WITNESS, sandbox_passed=None)
    assert not v.allowed
    assert any("no sandbox result" in r for r in v.reasons)


def test_a_patch_that_failed_in_the_sandbox_never_reaches_production() -> None:
    v = pc.evaluate(diff(), VERSIONED, DENIED, WITNESS, sandbox_passed=False)
    assert not v.allowed
    assert any("sandbox doing its job" in r for r in v.reasons)


# --- constraint 2: declared paths only -------------------------------------


@pytest.mark.parametrize("path", [
    "backend/rag.py",            # the source tree
    "backend/db.py",
    "docker-compose.yml",        # infrastructure
    "Dockerfile",
    ".env",
    "evaluation/evaluate.py",
    "tests/test_rag.py",
    "kavach.yaml",               # the safety policy itself
])
def test_a_patch_outside_the_declared_versioned_paths_is_refused(
    path: str,
) -> None:
    """§6.2.1: prompts and config files. Not the source tree, not tests, not
    infrastructure."""
    v = pc.evaluate(diff(path), VERSIONED, DENIED,
                    {**WITNESS, path: "whatever"}, sandbox_passed=True)
    assert not v.allowed, f"{path} was allowed"


@pytest.mark.parametrize("path", [
    "../Target_RAG-App/backend/rag.py",
    "prompts/../../etc/passwd",
    "/etc/passwd",
])
def test_a_path_that_escapes_the_repository_is_refused(path: str) -> None:
    v = pc.evaluate(diff(path), VERSIONED, DENIED,
                    {**WITNESS, path: "x"}, sandbox_passed=True)
    assert not v.allowed, f"{path} was allowed"


def test_a_manifest_with_no_versioned_paths_permits_nothing() -> None:
    """Fail closed: an operator who declared nothing healable gets nothing
    written, rather than a default."""
    v = pc.evaluate(diff(), {}, DENIED, WITNESS, sandbox_passed=True)
    assert not v.allowed
    assert any("declares no versioned_paths" in r for r in v.reasons)


# --- constraint 6: deny-list, on content as well as path -------------------


@pytest.mark.parametrize("line", [
    "EMBED_MODEL=all-MiniLM-L6-v2",
    "embedding_model: text-embedding-3-small",
    "DROP TABLE document_chunks;",
    "DELETE FROM document_chunks WHERE 1=1",
    "TRUNCATE document_chunks",
    "ALTER TABLE document_chunks ADD COLUMN x int",
    "run psql -c 'drop database ragdb'",
])
def test_denied_content_is_refused_even_on_an_allowed_path(line: str) -> None:
    """THE case the path check cannot catch. `prompts/answer.txt` is a
    permitted path; that does not make its contents permitted."""
    v = pc.evaluate(diff(added=[line]), VERSIONED, DENIED, WITNESS,
                    sandbox_passed=True)
    assert not v.allowed, f"a patch adding {line!r} was allowed"
    assert any("deny-list refuses on content" in r or "denied mutation" in r
               for r in v.reasons)


def test_removing_a_line_is_not_the_same_as_adding_one() -> None:
    """A diff that DELETES a reference to the corpus is not a diff that
    touches the corpus. Treating them alike would refuse safe patches and
    teach nobody anything."""
    v = pc.evaluate(diff(removed=["see document_chunks for details"],
                         added=["Answer from the context."]),
                    VERSIONED, DENIED, WITNESS, sandbox_passed=True)
    assert v.allowed, v.reasons


# --- constraint 5: diff budget ---------------------------------------------


def test_a_large_diff_is_not_a_repair() -> None:
    v = pc.evaluate(diff(added=[f"line {i}" for i in range(60)]),
                    VERSIONED, DENIED, WITNESS, sandbox_passed=True)
    assert not v.allowed
    assert any("over the budget" in r for r in v.reasons)


def test_touching_too_many_files_is_refused() -> None:
    many = "".join(
        f"--- a/prompts/p{i}.txt\n+++ b/prompts/p{i}.txt\n@@ -1 +1 @@\n+x\n"
        for i in range(4))
    witness = {f"prompts/p{i}.txt": "x" for i in range(4)}
    v = pc.evaluate(many, VERSIONED, DENIED, witness, sandbox_passed=True)
    assert not v.allowed
    assert any("files, over the budget" in r for r in v.reasons)


# --- constraint 3: an inverse must exist -----------------------------------


def test_a_file_with_no_witness_has_no_inverse_and_is_refused() -> None:
    """`executor/base.py` makes an action without an inverse unrepresentable.
    The same rule has to hold for a generated one."""
    v = pc.evaluate(diff("prompts/brand_new.txt"), VERSIONED, DENIED,
                    WITNESS, sandbox_passed=True)
    assert not v.allowed
    assert any("no inverse" in r for r in v.reasons)


# --- the shape rule: a diff, never a whole file ----------------------------


def test_a_whole_file_is_refused_because_it_cannot_fail_to_apply() -> None:
    """§6.2.1's reasoning: a diff against a known blob fails if the file
    moved; a whole-file write silently overwrites whatever is there."""
    v = pc.evaluate("You are a helpful assistant.\n{context}\n{question}\n",
                    VERSIONED, DENIED, WITNESS, sandbox_passed=True)
    assert not v.allowed
    assert any("not a unified diff" in r for r in v.reasons)


def test_an_empty_patch_is_refused() -> None:
    v = pc.evaluate("   ", VERSIONED, DENIED, WITNESS, sandbox_passed=True)
    assert not v.allowed


# --- the reporting property ------------------------------------------------


def test_every_reason_is_collected_not_just_the_first() -> None:
    """An operator reading a refusal should see everything wrong with the
    patch, not play whack-a-mole one rule at a time."""
    bad = diff("backend/db.py", added=["DROP TABLE document_chunks;"] * 30)
    v = pc.evaluate(bad, VERSIONED, DENIED, {}, sandbox_passed=None)
    assert len(v.reasons) >= 4, v.reasons


def test_the_tier_is_fixed_high_and_not_computed() -> None:
    """Constraint 1. A model-authored payload is HIGH whatever it claims to
    touch, so the tier is a property of the action, never of its parameters."""
    assert pc.RISK_TIER == "HIGH"
