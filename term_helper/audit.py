"""Append-only JSONL audit log (see Q19). No automatic rollback."""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone

from term_helper import config


def record(event: dict) -> None:
    config.ensure_dirs()
    payload = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    with config.AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def tail(count: int = 20) -> list[dict]:
    if not config.AUDIT_PATH.exists():
        return []
    with config.AUDIT_PATH.open("r", encoding="utf-8", errors="replace") as handle:
        lines = deque(handle, maxlen=count)
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
