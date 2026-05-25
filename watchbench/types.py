"""Shared data contracts for WatchBench evaluators."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Watch:
    watch_id: str
    watch_intent: str


@dataclass(frozen=True)
class EmailEvent:
    event_id: str
    timestamp: datetime
    thread_id: str
    from_name: str
    from_email: str
    to: list[str]
    cc: list[str]
    subject: str
    body: str
    attachments: list[str]

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "thread_id": self.thread_id,
            "from_name": self.from_name,
            "from_email": self.from_email,
            "to": self.to,
            "cc": self.cc,
            "subject": self.subject,
            "attachments": self.attachments,
        }

    @property
    def full_payload(self) -> dict[str, Any]:
        return {**self.metadata, "body": self.body}


@dataclass(frozen=True)
class GoldLabel:
    watch_id: str
    event_id: str
    should_wake: bool
    reason: str


@dataclass(frozen=True)
class CandidateWake:
    candidate: str
    watch_id: str
    event_id: str
    wake_time: datetime
    reason: str


@dataclass(frozen=True)
class Dataset:
    name: str
    stream: dict[str, Any]
    watches: list[Watch]
    events: list[EmailEvent]
    labels: list[GoldLabel]
