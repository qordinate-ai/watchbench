"""Candidate adapter interface."""

from __future__ import annotations

from typing import Protocol

from watchbench.costs import CostLedger
from watchbench.inbox import VirtualInbox
from watchbench.types import CandidateWake, Dataset, EmailEvent, Watch


class CandidateAdapter(Protocol):
    name: str

    def setup(
        self,
        *,
        dataset: Dataset,
        watches: list[Watch],
        inbox: VirtualInbox,
        cost: CostLedger,
    ) -> None:
        ...

    def on_event(self, event: EmailEvent) -> None:
        ...

    def on_tick(self) -> None:
        ...

    def flush(self) -> list[CandidateWake]:
        ...

    def teardown(self) -> None:
        ...
