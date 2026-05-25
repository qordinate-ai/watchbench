"""Timeline runner for candidate adapters."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from watchbench.adapters.base import CandidateAdapter
from watchbench.costs import CostLedger
from watchbench.inbox import VirtualInbox
from watchbench.scoring import ScoreResult, score_candidate
from watchbench.types import CandidateWake, Dataset


def subset_dataset(
    dataset: Dataset,
    *,
    max_events: int | None,
    max_watches: int | None = None,
    watch_ids: set[str] | None = None,
) -> Dataset:
    kept_events = dataset.events[:max_events] if max_events is not None else dataset.events
    kept_watches = dataset.watches
    if watch_ids:
        kept_watches = [watch for watch in kept_watches if watch.watch_id in watch_ids]
    if max_watches is not None:
        kept_watches = kept_watches[:max_watches]
    kept_event_ids = {event.event_id for event in kept_events}
    kept_watch_ids = {watch.watch_id for watch in kept_watches}
    return replace(
        dataset,
        events=kept_events,
        watches=kept_watches,
        labels=[
            label
            for label in dataset.labels
            if label.event_id in kept_event_ids and label.watch_id in kept_watch_ids
        ],
    )


def tick_times(start: datetime, end: datetime, *, interval: timedelta) -> list[datetime]:
    ticks: list[datetime] = []
    current = start
    while current <= end + interval:
        ticks.append(current)
        current += interval
    return ticks


def run_candidate(
    *,
    dataset: Dataset,
    adapter: CandidateAdapter,
    poll_interval: timedelta,
) -> tuple[ScoreResult, list[CandidateWake]]:
    cost = CostLedger()
    inbox = VirtualInbox(dataset.events, cost)
    adapter.setup(dataset=dataset, watches=dataset.watches, inbox=inbox, cost=cost)

    timeline: list[tuple[datetime, str, Any]] = []
    for event in dataset.events:
        timeline.append((event.timestamp, "event", event))
    if dataset.events:
        for tick in tick_times(
            dataset.events[0].timestamp,
            dataset.events[-1].timestamp,
            interval=poll_interval,
        ):
            timeline.append((tick, "tick", None))

    # Events at the exact tick timestamp become visible before the heartbeat runs.
    for timestamp, item_type, item in sorted(timeline, key=lambda row: (row[0], row[1] == "tick")):
        inbox.advance_to(timestamp)
        if item_type == "event":
            adapter.on_event(item)
        else:
            adapter.on_tick()

    wakes = adapter.flush()
    adapter.teardown()
    return (
        score_candidate(candidate=adapter.name, dataset=dataset, wakes=wakes, cost=cost),
        wakes,
    )
