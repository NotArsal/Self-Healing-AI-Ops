"""Exactly what the hash chain detects, and the one thing it does not.

ADDED 2026-11-05. `REPORT_DRAFT.md` §6 now states that the chain catches an
edited record and a deleted middle record, and does **not** catch a deletion
at the end. That claim was measured against a copy of the real log before it
was written down; this pins it so the claim and the code cannot drift apart.

WHY A TEST THAT ASSERTS A LIMITATION. The last test here asserts that tail
truncation passes verification, which looks like encoding a bug. It is
deliberate, for two reasons. A reader of `audit/log.py` should not have to
discover the boundary by experiment, and if someone later adds the signed
checkpoint that §9 item 16 describes, this test fails and makes them delete
it on purpose rather than quietly inheriting a stale guarantee.

The property the log actually buys, per `AGENTS.md`, is that Kavach cannot
act without leaving a record it then edits away. The first three tests are
that property. Tail truncation is outside it: an attacker who can delete the
end of the file can also stop the container.
"""

from __future__ import annotations

import json
from pathlib import Path

from kavach.audit.log import AuditLog


def _log(tmp_path: Path, rows: int = 12) -> AuditLog:
    log = AuditLog(tmp_path / "chain.jsonl")
    for i in range(rows):
        log.append("execute_done", incident_id=f"INC-{i:03d}", actor="kavach")
    return log


def _lines(log: AuditLog) -> list[str]:
    return log.path.read_text(encoding="utf-8").splitlines(True)


def test_an_untouched_chain_verifies() -> None:
    """A guard on the guard: if a fresh chain did not verify, every test
    below would pass for the wrong reason."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        log = _log(Path(d))
        check = log.verify()
        assert check.intact, check.detail
        assert check.rows == 12


def test_an_edited_record_is_caught(tmp_path: Path) -> None:
    """The digest is recomputed from each row's own payload, so changing
    content is caught even though every link still matches."""
    log = _log(tmp_path)
    lines = _lines(log)
    row = json.loads(lines[5])
    row["actor"] = "someone else"
    lines[5] = json.dumps(row) + "\n"
    log.path.write_text("".join(lines), encoding="utf-8")

    check = log.verify()
    assert not check.intact
    assert check.broken_at == 5
    assert "does not match its recorded hash" in check.detail


def test_a_deleted_middle_record_is_caught(tmp_path: Path) -> None:
    """The row after the hole carries a `prev` that now points at nothing
    in front of it."""
    log = _log(tmp_path)
    lines = _lines(log)
    del lines[5]
    log.path.write_text("".join(lines), encoding="utf-8")

    check = log.verify()
    assert not check.intact
    assert check.broken_at == 5
    assert "prev link" in check.detail


def test_a_reordered_pair_is_caught(tmp_path: Path) -> None:
    log = _log(tmp_path)
    lines = _lines(log)
    lines[4], lines[5] = lines[5], lines[4]
    log.path.write_text("".join(lines), encoding="utf-8")

    assert not log.verify().intact


def test_tail_truncation_is_not_caught_and_that_is_deliberate(
    tmp_path: Path,
) -> None:
    """THE BOUNDARY, asserted so it cannot be assumed away.

    Deleting records from the end leaves a chain that is valid from genesis
    and merely shorter, so `verify()` reports it intact. There is no seal key
    and no expected row count held outside the file.

    Measured the same way on the real log before §6 was written: 1014 rows
    intact, 964 rows after deleting the last 50, still reported intact.

    If this test ever fails, the chain has gained a length or checkpoint
    guarantee. That is a good thing - delete this test, and update
    `REPORT_DRAFT.md` §6 and §9 item 16, which currently say it has none.
    """
    log = _log(tmp_path)
    before = log.verify()
    assert before.intact and before.rows == 12

    lines = _lines(log)
    log.path.write_text("".join(lines[:-4]), encoding="utf-8")

    after = log.verify()
    assert after.rows == 8, "the truncation did not take effect"
    assert after.intact, (
        "the chain now detects tail truncation. That is an improvement, not "
        "a failure: delete this test and correct REPORT_DRAFT.md §6 and §9 "
        "item 16, which both state that it does not.")
