"""A Gmail-like virtual inbox used by all candidate adapters."""

from __future__ import annotations

from datetime import datetime

from watchbench.costs import CostLedger
from watchbench.types import EmailEvent


class VirtualInbox:
    """Exposes source events through a tool-like interface.

    Polling candidates should use this instead of direct dataset access. The
    cost ledger records every list/search/body read, so a heartbeat-style agent
    pays for repeatedly inspecting a noisy inbox.
    """

    def __init__(self, events: list[EmailEvent], cost: CostLedger) -> None:
        self._events = sorted(events, key=lambda event: event.timestamp)
        self._by_id = {event.event_id: event for event in self._events}
        self._visible_until: datetime | None = None
        self._cost = cost

    def advance_to(self, now: datetime) -> None:
        self._visible_until = now

    @property
    def current_time(self) -> datetime:
        if self._visible_until is None:
            raise RuntimeError("VirtualInbox has not been advanced yet")
        return self._visible_until

    def visible_events(self) -> list[EmailEvent]:
        if self._visible_until is None:
            return []
        return [event for event in self._events if event.timestamp <= self._visible_until]

    def list_messages(self, *, after_event_id: str | None = None, limit: int | None = None) -> list[dict]:
        visible = self.visible_events()
        if after_event_id:
            index = next(
                (idx for idx, event in enumerate(visible) if event.event_id == after_event_id),
                None,
            )
            visible = visible[index + 1 :] if index is not None else visible
        if limit is not None:
            visible = visible[:limit]
        self._cost.source_list_calls += 1
        self._cost.source_metadata_returned += len(visible)
        return [event.metadata for event in visible]

    def search_messages(self, query: str, *, limit: int | None = None) -> list[dict]:
        query_lower = query.lower()
        matches = [
            event
            for event in self.visible_events()
            if query_lower in event.subject.lower()
            or query_lower in event.body.lower()
            or query_lower in event.from_email.lower()
            or query_lower in event.from_name.lower()
        ]
        if limit is not None:
            matches = matches[:limit]
        self._cost.source_search_calls += 1
        self._cost.source_metadata_returned += len(matches)
        return [event.metadata for event in matches]

    def get_message(self, event_id: str) -> dict:
        event = self._by_id[event_id]
        if self._visible_until is not None and event.timestamp > self._visible_until:
            raise ValueError(f"{event_id} is not visible yet")
        self._cost.source_get_calls += 1
        self._cost.source_bodies_returned += 1
        return event.full_payload
