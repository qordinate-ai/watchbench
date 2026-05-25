#!/usr/bin/env python3
"""Export WatchBench datasets into Hugging Face-friendly JSONL tables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from watchbench.dataset import load_dataset

EXPORTS = [
    ("full", Path("data/watchbench-email-v0-full")),
    ("mini", Path("data/watchbench-email-v0-mini")),
]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def event_row(event) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "timestamp": event.timestamp.isoformat(),
        "thread_id": event.thread_id,
        "from_name": event.from_name,
        "from_email": event.from_email,
        "to": event.to,
        "cc": event.cc,
        "subject": event.subject,
        "body": event.body,
        "attachments": event.attachments,
    }


def export_split(name: str, dataset_dir: Path) -> dict[str, int]:
    dataset = load_dataset(dataset_dir)
    out_dir = Path("hf") / name
    events = {event.event_id: event for event in dataset.events}
    watches = {watch.watch_id: watch for watch in dataset.watches}

    pair_rows: list[dict[str, Any]] = []
    for label in dataset.labels:
        event = events[label.event_id]
        watch = watches[label.watch_id]
        pair_rows.append(
            {
                "dataset": dataset.name,
                "watch_id": watch.watch_id,
                "watch_intent": watch.watch_intent,
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat(),
                "thread_id": event.thread_id,
                "from_name": event.from_name,
                "from_email": event.from_email,
                "to": event.to,
                "cc": event.cc,
                "subject": event.subject,
                "body": event.body,
                "attachments": event.attachments,
                "should_wake": label.should_wake,
                "reason": label.reason,
            }
        )

    write_jsonl(out_dir / "pairs.jsonl", pair_rows)
    write_jsonl(out_dir / "events.jsonl", [event_row(event) for event in dataset.events])
    write_jsonl(out_dir / "watches.jsonl", [watch.__dict__ for watch in dataset.watches])
    write_jsonl(out_dir / "labels.jsonl", [label.__dict__ for label in dataset.labels])
    (out_dir / "manifest.json").write_text(
        (dataset_dir / "manifest.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return {
        "events": len(dataset.events),
        "watches": len(dataset.watches),
        "labels": len(dataset.labels),
        "pairs": len(pair_rows),
        "positive_pairs": sum(1 for row in pair_rows if row["should_wake"]),
    }


def main() -> int:
    summary = {name: export_split(name, path) for name, path in EXPORTS}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
