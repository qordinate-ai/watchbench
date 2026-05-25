"""Gold-label adapter used only to verify the harness scorer."""

from __future__ import annotations

from watchbench.costs import CostLedger
from watchbench.inbox import VirtualInbox
from watchbench.types import CandidateWake, Dataset, EmailEvent, Watch


class OracleAdapter:
    name = "gold-oracle"

    def setup(
        self,
        *,
        dataset: Dataset,
        watches: list[Watch],
        inbox: VirtualInbox,
        cost: CostLedger,
    ) -> None:
        self._labels = {
            (label.watch_id, label.event_id): label for label in dataset.labels if label.should_wake
        }
        self._wakes: list[CandidateWake] = []

    def on_event(self, event: EmailEvent) -> None:
        for (watch_id, event_id), label in self._labels.items():
            if event_id == event.event_id:
                self._wakes.append(
                    CandidateWake(
                        candidate=self.name,
                        watch_id=watch_id,
                        event_id=event.event_id,
                        wake_time=event.timestamp,
                        reason=label.reason,
                    )
                )

    def on_tick(self) -> None:
        return

    def flush(self) -> list[CandidateWake]:
        return list(self._wakes)

    def teardown(self) -> None:
        return
