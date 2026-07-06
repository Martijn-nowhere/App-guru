"""
The shared, append-only history of everything app-guru has ever found.

Design (settled after a design review, kept deliberately minimal):

- One JSONL file, committed to the repo -- not secret, and the whole point
  of a monthly cadence tool is that results should compound across runs
  instead of disappearing into one-off CSVs.
- Append-only: every check writes a NEW entry, nothing is ever edited or
  overwritten in place. "Current status" of an idea is whatever the reader
  computes from the full history, not a mutable field.
- No cross-station "signal" state machine. `verdict` is only ever a real,
  objective result: RISING / FLAT / DECLINING from `trends`. `mine` entries
  always write `verdict: None` -- a pain point is a research lead, never a
  claim of validated demand. Only trends data (or, later, real landing-page
  signups) can call something validated.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_LEDGER_PATH = Path(__file__).resolve().parent.parent / "data" / "ledger.jsonl"


@dataclass
class LedgerEntry:
    station: str
    subject: str
    verdict: str | None
    data: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    ts: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


def append_to_ledger(entries: list[LedgerEntry], path: Path | str = DEFAULT_LEDGER_PATH) -> None:
    """Append entries to the JSONL ledger, one JSON object per line. Creates
    the file (and its parent directory) if it doesn't exist yet."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(asdict(entry), ensure_ascii=False))
            f.write("\n")


def read_ledger(path: Path | str = DEFAULT_LEDGER_PATH) -> list[LedgerEntry]:
    """Read every entry ever recorded. Returns [] if the ledger doesn't exist yet."""
    path = Path(path)
    if not path.exists():
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            entries.append(LedgerEntry(**raw))
    return entries


def validated_subjects(path: Path | str = DEFAULT_LEDGER_PATH) -> list[str]:
    """Subjects with at least one RISING trends entry anywhere in their
    history -- the only thing this ledger considers "validated"."""
    seen = set()
    result = []
    for entry in read_ledger(path):
        if entry.verdict == "RISING" and entry.subject not in seen:
            seen.add(entry.subject)
            result.append(entry.subject)
    return result
