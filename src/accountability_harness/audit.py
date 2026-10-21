"""JSONL audit log: one file per agent run, one JSON line per event."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .governance import canonical

GENESIS = "0" * 64  # the prev_hash of a log's first entry


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLog:
    """Writes and reads the per-run audit log.

    The log is a JSONL file: each event is appended as one JSON line as
    the run proceeds. Entry types: "run_meta", "scope", "action",
    "mutation", "run_end". The harness only appends, but the file itself
    is an ordinary file: anyone with write access can edit it.

    The log is tamper-evident, not tamper-proof. Each entry carries the
    SHA-256 of the previous entry (prev_hash; GENESIS for the first) and
    of itself (hash), both over the canonical JSON. verify() detects an
    edited, deleted or reordered line. It does not prevent edits, and it
    cannot detect a rewrite of the whole file with fresh hashes, or lines
    cut from the end, unless the final hash is kept somewhere else.

    The log can contain tool arguments and outputs (for example message
    text), truncated to the Harness max_text limit. Treat it as
    sensitive data.
    """

    def __init__(self, log_dir: str | Path, run_id: str | None = None):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or str(uuid4())
        self.path = self.log_dir / f"audit-{self.run_id}.jsonl"
        self._seq = 0
        self._prev = GENESIS

    def _write(self, entry: dict[str, Any]) -> None:
        entry = {"run_id": self.run_id, "logged_at": utcnow_iso(), **entry, "prev_hash": self._prev}
        entry["hash"] = self._prev = _digest(entry)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def write_meta(self, agent_name: str, **extra: Any) -> None:
        self._write({"type": "run_meta", "agent_name": agent_name, **extra})

    def write_scope(self, scope_dict: dict[str, Any], **extra: Any) -> None:
        self._write({"type": "scope", "scope": scope_dict, **extra})

    def write_action(self, action: dict[str, Any]) -> dict[str, Any]:
        self._seq += 1
        entry = {"type": "action", "seq": self._seq, **action}
        self._write(entry)
        return entry

    def write_mutation(self, mutation: dict[str, Any]) -> None:
        self._write({"type": "mutation", **mutation})

    def write_end(self, summary: dict[str, Any]) -> None:
        self._write({"type": "run_end", **summary})

    def read(self) -> Iterator[dict[str, Any]]:
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)


def _digest(entry: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(entry).encode("utf-8")).hexdigest()


def verify(log_path: str | Path) -> tuple[str, int]:
    """Check a log's hash chain.

    Returns ("intact", number of entries), ("broken", first line number
    where the chain fails), or ("not chained", 0) for a log written
    before the chain existed.
    """
    return verify_text(Path(log_path).read_text(encoding="utf-8"))


def verify_text(text: str) -> tuple[str, int]:
    """verify() for a log held in memory, as text."""
    prev, count = GENESIS, 0
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            return "broken", number
        if count == 0 and "hash" not in entry:
            return "not chained", 0
        claimed = entry.pop("hash", None)
        if entry.get("prev_hash") != prev or claimed != _digest(entry):
            return "broken", number
        prev, count = claimed, count + 1
    return "intact", count
