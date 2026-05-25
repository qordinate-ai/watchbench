"""Generic heartbeat/cron-style polling agent baseline."""

from __future__ import annotations

import json

from watchbench.costs import CostLedger
from watchbench.inbox import VirtualInbox
from watchbench.llm import JsonLLMClient
from watchbench.prompts import render_prompt
from watchbench.types import CandidateWake, Dataset, EmailEvent, Watch


class PollingAgentAdapter:
    """Models a native agent heartbeat that periodically scans the inbox.

    The adapter deliberately talks through VirtualInbox instead of direct dataset
    access. That lets the evaluator charge for source reads and later swap this
    class for OpenClaw/Hermes-specific runtimes without changing scoring.
    """

    name = "generic-llm-polling-agent"

    def __init__(self, *, llm: JsonLLMClient, metadata_limit: int | None = None) -> None:
        self._llm = llm
        self._metadata_limit = metadata_limit

    def setup(
        self,
        *,
        dataset: Dataset,
        watches: list[Watch],
        inbox: VirtualInbox,
        cost: CostLedger,
    ) -> None:
        self._stream = dataset.stream
        self._watches = watches
        self._inbox = inbox
        self._cost = cost
        self._last_seen_event_id: str | None = None
        self._wakes: list[CandidateWake] = []
        self._seen_wakes: set[tuple[str, str]] = set()

    def on_event(self, event: EmailEvent) -> None:
        return

    def on_tick(self) -> None:
        metadata_rows = self._inbox.list_messages(
            after_event_id=self._last_seen_event_id,
            limit=self._metadata_limit,
        )
        if not metadata_rows:
            return
        full_events = [self._inbox.get_message(row["event_id"]) for row in metadata_rows]
        self._last_seen_event_id = metadata_rows[-1]["event_id"]
        prompt = render_prompt(
            "eval/polling_agent_tick.md",
            stream_user_json=json.dumps(self._stream.get("user", {}), ensure_ascii=False, indent=2),
            watches_json=json.dumps([watch.__dict__ for watch in self._watches], ensure_ascii=False, indent=2),
            events_json=json.dumps(full_events, ensure_ascii=False, indent=2),
        )
        llm_result = self._llm.complete_json(
            prompt,
            max_tokens=5000,
            temperature=0.0,
            call_name=f"polling_tick_{metadata_rows[0]['event_id']}_{metadata_rows[-1]['event_id']}",
        )
        result = llm_result.parsed
        self._cost.record_llm_usage(llm_result.usage)
        if not isinstance(result, list):
            raise RuntimeError(f"Bad polling result: {result}")
        visible_event_ids = {row["event_id"] for row in metadata_rows}
        valid_watch_ids = {watch.watch_id for watch in self._watches}
        for row in result:
            if not row.get("should_wake", True):
                continue
            watch_id = row.get("watch_id")
            event_id = row.get("event_id")
            if watch_id not in valid_watch_ids or event_id not in visible_event_ids:
                raise RuntimeError(f"Polling agent returned out-of-scope wake: {row}")
            key = (watch_id, event_id)
            if key in self._seen_wakes:
                continue
            self._seen_wakes.add(key)
            self._wakes.append(
                CandidateWake(
                    candidate=self.name,
                    watch_id=watch_id,
                    event_id=event_id,
                    wake_time=self._inbox.current_time,
                    reason=str(row.get("reason", "")),
                )
            )

    def flush(self) -> list[CandidateWake]:
        return list(self._wakes)

    def teardown(self) -> None:
        return
