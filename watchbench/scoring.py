"""Score candidate wakeups against gold labels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Any

from watchbench.costs import CostLedger
from watchbench.types import CandidateWake, Dataset


@dataclass(frozen=True)
class ScoreResult:
    candidate: str
    metrics: dict[str, Any]


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return ordered[index]


def score_candidate(
    *,
    candidate: str,
    dataset: Dataset,
    wakes: list[CandidateWake],
    cost: CostLedger,
) -> ScoreResult:
    gold = {(label.watch_id, label.event_id) for label in dataset.labels if label.should_wake}
    event_times: dict[str, datetime] = {event.event_id: event.timestamp for event in dataset.events}
    predicted_ordered = [(wake.watch_id, wake.event_id) for wake in wakes]
    predicted = set(predicted_ordered)
    duplicate_wakes = len(predicted_ordered) - len(predicted)

    true_positive = len(predicted & gold)
    false_positive = len(predicted - gold)
    false_negative = len(gold - predicted)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(gold) if gold else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    latencies = [
        max(0.0, (wake.wake_time - event_times[wake.event_id]).total_seconds())
        for wake in wakes
        if (wake.watch_id, wake.event_id) in gold and wake.event_id in event_times
    ]

    first_ts = min(event_times.values())
    last_ts = max(event_times.values())
    stream_days = max(1 / 24, (last_ts - first_ts).total_seconds() / 86400)
    metrics = {
        "candidate": candidate,
        "gold_positive_count": len(gold),
        "wake_count": len(wakes),
        "unique_wake_count": len(predicted),
        "duplicate_wake_count": duplicate_wakes,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_wakeups_per_day": false_positive / stream_days,
        "latency_seconds_p50": median(latencies) if latencies else None,
        "latency_seconds_p95": percentile(latencies, 0.95),
        "latency_seconds_max": max(latencies) if latencies else None,
        "cost": cost.as_dict(),
    }
    return ScoreResult(candidate=candidate, metrics=metrics)
