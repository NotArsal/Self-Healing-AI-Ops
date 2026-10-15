"""Append-only, hash-chained audit log — `FR` audit trail, `ARCHITECTURE.md` §6.

Every row carries the hash of the row before it. Changing or deleting any
earlier row breaks every hash after it, and `verify()` says exactly where. That
is tamper *evidence*, not tamper *proofing*: anyone who can write the file can
rewrite the whole chain. It is the right guarantee for a system whose claim is
"you can audit what the agent did", and it must not be described as more.

WHY A FILE AND NOT A TABLE
Postgres arrives with incident persistence. The chain's value does not depend
on where it is stored, and the writer's interface does not change when it moves
— `append()` takes an event and returns a row. Waiting for the database would
mean shipping the safety engine with no audit trail, which is the wrong order:
the gate and the record of what the gate decided belong together.

THERE IS NO UPDATE AND NO DELETE
Not "they are discouraged" — they are not written. The file is opened in append
mode and nothing in this module seeks. `DESIGN_SYSTEM.md` §7.10 says the audit
view has no edit control anywhere and that the absence is the point; this is
the same statement one layer down.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _digest(previous: str, payload: str) -> str:
    return hashlib.sha256(f"{previous}{payload}".encode()).hexdigest()


@dataclass
class ChainCheck:
    """The result of verifying a chain. Never raises; always reports."""

    rows: int = 0
    intact: bool = True
    broken_at: int | None = None
    detail: str = ""
    malformed: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "intact": self.intact,
            "broken_at": self.broken_at,
            "detail": self.detail,
            "malformed": self.malformed,
        }

    def render(self) -> str:
        if self.intact:
            return f"Audit chain intact: {self.rows} rows"
        return f"CHAIN BROKEN at row {self.broken_at}: {self.detail}"


class AuditLog:
    """One append-only hash-chained JSONL file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Serialises writers inside one process. Across processes the append
        # mode below keeps whole lines intact on POSIX and Windows for the row
        # sizes written here; a shared log across replicas needs the database.
        self._lock = threading.Lock()

    # --- writing ------------------------------------------------------------

    def _last_hash(self) -> str:
        """The hash of the final row, or GENESIS for an empty log."""
        if not self.path.exists():
            return GENESIS
        last = ""
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = line
        if not last:
            return GENESIS
        try:
            return str(json.loads(last)["hash"])
        except (json.JSONDecodeError, KeyError, TypeError):
            # A corrupt tail must not silently restart the chain, because that
            # is precisely what tampering looks like. Chain from the raw text
            # so verify() reports a break here rather than hiding it.
            return _digest(GENESIS, last.strip())

    def append(
        self,
        event: str,
        incident_id: str = "",
        actor: str = "kavach",
        **fields: Any,
    ) -> dict[str, Any]:
        """Write one row. Returns the row as stored, including its hash."""
        with self._lock:
            previous = self._last_hash()
            row: dict[str, Any] = {
                "at": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "incident_id": incident_id,
                "actor": actor,
                "event": event,
                **fields,
            }
            # The hash covers the payload and the previous hash, and excludes
            # the hash field itself so the digest is reproducible from the row.
            payload = json.dumps(row, sort_keys=True, separators=(",", ":"),
                                 default=str)
            row["prev"] = previous
            row["hash"] = _digest(previous, payload)

            line = json.dumps(row, sort_keys=True, separators=(",", ":"),
                              default=str)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            return row

    # --- reading ------------------------------------------------------------

    def rows(self, limit: int = 0) -> list[dict[str, Any]]:
        """Every row, oldest first. `limit` returns the newest N."""
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    out.append({"_malformed": line.rstrip("\n")})
        return out[-limit:] if limit else out

    def verify(self) -> ChainCheck:
        """Walk the chain and report the first break.

        Recomputes each row's digest from its own payload, so a row whose
        CONTENT was edited is caught as well as one whose links were.
        """
        check = ChainCheck()
        previous = GENESIS
        for index, row in enumerate(self.rows()):
            check.rows += 1
            if "_malformed" in row:
                check.malformed.append(index)
                check.intact = False
                if check.broken_at is None:
                    check.broken_at = index
                    check.detail = "row is not valid JSON"
                return check

            stored_hash = row.get("hash")
            stored_prev = row.get("prev")
            if not isinstance(stored_hash, str) or not isinstance(stored_prev, str):
                check.intact = False
                check.broken_at = index
                check.detail = "row is missing its hash or prev link"
                return check

            if stored_prev != previous:
                check.intact = False
                check.broken_at = index
                check.detail = (
                    f"prev link is {stored_prev[:12]}…, expected {previous[:12]}… "
                    f"- a row before this one was changed or removed"
                )
                return check

            payload_row = {k: v for k, v in row.items() if k not in ("hash", "prev")}
            payload = json.dumps(payload_row, sort_keys=True, separators=(",", ":"),
                                 default=str)
            if _digest(stored_prev, payload) != stored_hash:
                check.intact = False
                check.broken_at = index
                check.detail = "row content does not match its recorded hash"
                return check

            previous = stored_hash

        return check
