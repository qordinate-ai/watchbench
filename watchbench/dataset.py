"""Load checked-in WatchBench datasets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from watchbench.types import Dataset, EmailEvent, GoldLabel, Watch


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_dataset(path: Path) -> Dataset:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    stream = json.loads((path / "stream.json").read_text(encoding="utf-8"))
    watches = [
        Watch(watch_id=row["watch_id"], watch_intent=row["watch_intent"])
        for row in read_jsonl(path / "watches.jsonl")
    ]
    events = [
        EmailEvent(
            event_id=row["event_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            thread_id=row["thread_id"],
            from_name=row["from_name"],
            from_email=row["from_email"],
            to=list(row.get("to", [])),
            cc=list(row.get("cc", [])),
            subject=row["subject"],
            body=row["body"],
            attachments=list(row.get("attachments", [])),
        )
        for row in read_jsonl(path / "events.jsonl")
    ]
    labels = [
        GoldLabel(
            watch_id=row["watch_id"],
            event_id=row["event_id"],
            should_wake=bool(row["should_wake"]),
            reason=row.get("reason", ""),
        )
        for row in read_jsonl(path / "labels.jsonl")
    ]
    return Dataset(
        name=str(manifest["name"]),
        stream=stream,
        watches=watches,
        events=sorted(events, key=lambda event: event.timestamp),
        labels=labels,
    )
