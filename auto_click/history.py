"""Persistent task history for the GUI."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import config


HISTORY_FILE = Path(getattr(config, "BASE_DIR", Path.cwd())) / "history" / "tasks.jsonl"
_MAX_FILE_SIZE_MB = 10
_MAX_FILE_SIZE = _MAX_FILE_SIZE_MB * 1024 * 1024


def append_task_history(record: dict[str, Any]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "id": record.get("id") or uuid.uuid4().hex,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **record,
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False) + "\n")
    _trim_if_needed()


def load_task_history(limit: int = 100) -> list[dict[str, Any]]:
    if not HISTORY_FILE.exists():
        return []
    records: list[dict[str, Any]] = []
    with open(HISTORY_FILE, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                value.setdefault("_index", len(records))
                records.append(value)
    return records[-limit:]


def _trim_if_needed() -> None:
    """Keep only the most recent records when the file exceeds the size limit."""
    try:
        size = os.path.getsize(str(HISTORY_FILE))
    except OSError:
        return
    if size <= _MAX_FILE_SIZE:
        return
    records = load_task_history(limit=100000)
    keep = [dict(record) for record in records]
    for record in keep:
        record.pop("_index", None)
    while len(keep) > 1 and _records_size(keep) > _MAX_FILE_SIZE:
        drop_count = max(1, len(keep) // 10)
        keep = keep[drop_count:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as handle:
        for record in keep:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _records_size(records: list[dict[str, Any]]) -> int:
    return sum(
        len(json.dumps(record, ensure_ascii=False).encode("utf-8")) + 1
        for record in records
    )


def delete_task_history(record_id: str = "", index: int | None = None) -> None:
    records = load_task_history(limit=100000)
    kept: list[dict[str, Any]] = []
    for idx, record in enumerate(records):
        matched = bool(record_id and record.get("id") == record_id)
        if index is not None and int(record.get("_index", idx)) == index:
            matched = True
        if not matched:
            cleaned = dict(record)
            cleaned.pop("_index", None)
            kept.append(cleaned)

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as handle:
        for record in kept:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
