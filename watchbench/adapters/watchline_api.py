"""Adapter for the real Watchline HTTP API."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from watchbench.adapters.openclaw_polling import OpenClawConfig, invoke_openclaw_json
from watchbench.costs import CostLedger
from watchbench.http_json import post_json
from watchbench.inbox import VirtualInbox
from watchbench.llm import JsonLLMClient
from watchbench.prompts import render_prompt
from watchbench.types import CandidateWake, Dataset, EmailEvent, GoldLabel, Watch

GMAIL_APP = "gmail"
GMAIL_EVENT_TYPE = "gmail_email_received"
GOOGLE_CALENDAR_APP = "google_calendar"
GOOGLE_CALENDAR_EVENT_TYPE = "google_calendar_event_created"


class WatchlineApiAdapter:
    """Runs the benchmark through Watchline's public API surface.

    The adapter creates one Watchline watch per benchmark watch, pushes each
    email through `/v1/events.ingest`, then polls a pull channel for matched
    deliveries. That mirrors the OpenClaw/local-agent setup: Watchline owns
    filtering, while the local agent wakes only when the pull channel has work.
    """

    name = "watchline-api"

    def __init__(
        self,
        *,
        api_base_url: str,
        api_key: str,
        channel_id: str,
        user_id: str,
        downstream_openclaw: OpenClawConfig | None = None,
        setup_responder: JsonLLMClient | None = None,
        max_setup_turns: int = 4,
        poll_limit: int = 200,
        timeout_seconds: int = 900,
    ) -> None:
        self._base = api_base_url.rstrip("/")
        self._api_key = api_key
        self._channel_id = channel_id
        self._user_id = user_id
        self._downstream_openclaw = downstream_openclaw
        self._setup_responder = setup_responder
        self._max_setup_turns = max_setup_turns
        self._poll_limit = poll_limit
        self._timeout_seconds = timeout_seconds

    def setup(
        self,
        *,
        dataset: Dataset,
        watches: list[Watch],
        inbox: VirtualInbox,
        cost: CostLedger,
    ) -> None:
        self._inbox = inbox
        self._cost = cost
        self._wakes: list[CandidateWake] = []
        self._seen_deliveries: set[str] = set()
        self._real_to_dataset_watch: dict[str, str] = {}
        self._watch_by_id = {watch.watch_id: watch for watch in watches}
        self._event_by_id = {event.event_id: event for event in dataset.events}
        self._positive_labels_by_watch = labels_by_watch(dataset.labels, should_wake=True)
        self._negative_labels_by_watch = labels_by_watch(dataset.labels, should_wake=False)
        self._stream_user = dataset.stream.get("user", {})
        self._first_event_time = dataset.events[0].timestamp if dataset.events else datetime.now(timezone.utc)
        self._api_start_time = datetime.now(timezone.utc)
        self._cost.notes.append("watchline_service_matching_cost_out_of_scope")
        if self._downstream_openclaw:
            self._cost.notes.append(f"watchline_downstream_openclaw_session_id={self._downstream_openclaw.session_id}")
        self._ensure_ingest_connection(dataset)
        for watch in watches:
            self._create_watch(watch)

    def on_event(self, event: EmailEvent) -> None:
        self._ingest_event(event)

    def on_tick(self) -> None:
        self._drain_pending_deliveries()

    def flush(self) -> list[CandidateWake]:
        self._drain_pending_deliveries()
        return list(self._wakes)

    def teardown(self) -> None:
        return

    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self._api_key}"}

    def _url(self, path: str) -> str:
        return f"{self._base}/v1/{path}"

    def _ensure_ingest_connection(self, dataset: Dataset) -> None:
        seed_time = self._api_start_time - timedelta(seconds=1)
        for app, event_type in [
            (GMAIL_APP, GMAIL_EVENT_TYPE),
            (GOOGLE_CALENDAR_APP, GOOGLE_CALENDAR_EVENT_TYPE),
        ]:
            post_json(
                url=self._url("events.ingest"),
                headers=self._headers(),
                timeout_seconds=self._timeout_seconds,
                payload={
                    "user_id": self._user_id,
                    "app": app,
                    "event_type": event_type,
                    "source_event_id": f"{dataset.name}:{app}:connection_seed",
                    "occurred_at": watchline_datetime(seed_time),
                    "payload": {
                        "event_id": f"{dataset.name}:{app}:connection_seed",
                        "subject": "WatchBench connection seed",
                        "body": "Synthetic seed event used only to materialize the benchmark source connection.",
                    },
                },
            )
        self._cost.notes.append("watchline_api_source_connections=events.ingest")

    def _create_watch(self, watch: Watch) -> None:
        response = post_json(
            url=self._url("watches.create"),
            headers=self._headers(),
            timeout_seconds=self._timeout_seconds,
            payload={
                "channel_id": self._channel_id,
                "user_id": self._user_id,
                "intent": watch.watch_intent,
            },
        )
        response = self._continue_setup_until_terminal(watch, response)
        status = response.get("status")
        if status != "active":
            raise RuntimeError(f"Watchline did not activate {watch.watch_id}: {response}")
        real_watch_id = response.get("watch_id")
        if not isinstance(real_watch_id, str) or not real_watch_id:
            raise RuntimeError(f"Watchline returned an invalid watch id for {watch.watch_id}: {response}")
        self._real_to_dataset_watch[real_watch_id] = watch.watch_id

    def _continue_setup_until_terminal(self, watch: Watch, response: dict[str, Any]) -> dict[str, Any]:
        for turn in range(self._max_setup_turns):
            status = response.get("status")
            if status in {"active", "declined"}:
                return response
            if status != "needs_input":
                return response
            if not self._setup_responder:
                return response
            watchline_watch_id = response.get("watch_id")
            question = response.get("message")
            if not isinstance(watchline_watch_id, str) or not isinstance(question, str):
                return response
            answer = self._answer_setup_question(watch=watch, question=question, turn=turn + 1)
            response = post_json(
                url=self._url("watches.continue"),
                headers=self._headers(),
                timeout_seconds=self._timeout_seconds,
                payload={
                    "watch_id": watchline_watch_id,
                    "user_id": self._user_id,
                    "message": answer,
                },
            )
        return response

    def _answer_setup_question(self, *, watch: Watch, question: str, turn: int) -> str:
        if not self._setup_responder:
            raise RuntimeError("setup responder is not configured")
        prompt = render_prompt(
            "eval/watchline_setup_reply.md",
            user_json=json.dumps(self._stream_user, ensure_ascii=False, indent=2),
            watch_intent=watch.watch_intent,
            question=question,
            positive_examples_json=json.dumps(
                setup_examples(watch.watch_id, self._positive_labels_by_watch, self._event_by_id),
                ensure_ascii=False,
                indent=2,
            ),
            negative_examples_json=json.dumps(
                setup_examples(watch.watch_id, self._negative_labels_by_watch, self._event_by_id),
                ensure_ascii=False,
                indent=2,
            ),
        )
        result = self._setup_responder.complete_json(
            prompt,
            max_tokens=1200,
            temperature=0.0,
            call_name=f"watchline_setup_reply_{watch.watch_id}_{turn}",
        )
        self._cost.record_llm_usage(result.usage)
        parsed = result.parsed
        if not isinstance(parsed, dict) or "message" not in parsed:
            raise RuntimeError(f"Bad setup reply for {watch.watch_id}: {parsed}")
        message = parsed["message"]
        if not isinstance(message, str):
            message = json.dumps(message, ensure_ascii=False)
        self._cost.notes.append(f"watchline_setup_reply={watch.watch_id}:turn_{turn}")
        return message

    def _ingest_event(self, event: EmailEvent) -> None:
        self._cost.source_get_calls += 1
        self._cost.source_bodies_returned += 1
        response = post_json(
            url=self._url("events.ingest"),
            headers=self._headers(),
            timeout_seconds=self._timeout_seconds,
            payload={
                "user_id": self._user_id,
                "app": GMAIL_APP,
                "event_type": GMAIL_EVENT_TYPE,
                "source_event_id": event.event_id,
                "occurred_at": watchline_datetime(self._api_event_time(event.timestamp)),
                "payload": event.full_payload,
            },
        )
        if response.get("dropped_oversized"):
            self._cost.notes.append(f"watchline_dropped_oversized={event.event_id}")

    def _drain_pending_deliveries(self) -> None:
        while True:
            response = post_json(
                url=self._url("deliveries.pending"),
                headers=self._headers(),
                timeout_seconds=self._timeout_seconds,
                payload={"channel_id": self._channel_id, "limit": self._poll_limit},
            )
            deliveries = response.get("data", [])
            if not isinstance(deliveries, list):
                raise RuntimeError(f"Bad Watchline pending delivery response: {response}")
            if not deliveries:
                return
            ack_ids: list[str] = []
            for delivery in deliveries:
                self._handle_delivery(delivery)
                delivery_id = delivery.get("delivery_id")
                if isinstance(delivery_id, str):
                    ack_ids.append(delivery_id)
            if ack_ids:
                post_json(
                    url=self._url("deliveries.ack"),
                    headers=self._headers(),
                    timeout_seconds=self._timeout_seconds,
                    payload={"channel_id": self._channel_id, "delivery_ids": ack_ids},
                )
            if not response.get("next_cursor"):
                return

    def _handle_delivery(self, delivery: dict[str, Any]) -> None:
        delivery_id = delivery.get("delivery_id")
        if not isinstance(delivery_id, str) or delivery_id in self._seen_deliveries:
            return
        self._seen_deliveries.add(delivery_id)
        if delivery.get("type") != "watchline.match":
            self._cost.notes.append(f"watchline_control_delivery={delivery.get('type')}")
            return
        real_watch_id = delivery.get("watch_id")
        watch_id = self._real_to_dataset_watch.get(str(real_watch_id))
        source = delivery.get("source", {})
        event_id = source.get("source_event_id") if isinstance(source, dict) else None
        if not watch_id or not isinstance(event_id, str):
            raise RuntimeError(f"Watchline delivery cannot be mapped back to dataset ids: {delivery}")
        self._process_downstream_openclaw(watch_id=watch_id, event_id=event_id)
        self._wakes.append(
            CandidateWake(
                candidate=self.name,
                watch_id=watch_id,
                event_id=event_id,
                wake_time=self._inbox.current_time,
                reason=str(delivery.get("intent", "")),
            )
        )

    def _process_downstream_openclaw(self, *, watch_id: str, event_id: str) -> None:
        if not self._downstream_openclaw:
            return
        watch = self._watch_by_id.get(watch_id)
        event = self._event_by_id.get(event_id)
        if not watch or not event:
            raise RuntimeError(f"Cannot process downstream OpenClaw wake for {watch_id}/{event_id}")
        prompt = render_prompt(
            "eval/watchline_delivery_openclaw.md",
            watch_json=json.dumps(watch.__dict__, ensure_ascii=False, indent=2),
            event_json=json.dumps(event.full_payload, ensure_ascii=False, indent=2),
        )
        parsed, usage = invoke_openclaw_json(prompt, self._downstream_openclaw)
        self._cost.record_llm_usage(usage)
        if not isinstance(parsed, dict) or not parsed.get("processed"):
            raise RuntimeError(f"Downstream OpenClaw did not process Watchline delivery: {parsed}")

    def _api_event_time(self, timestamp: datetime) -> datetime:
        return self._api_start_time + (timestamp - self._first_event_time)


def watchline_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def labels_by_watch(labels: list[GoldLabel], *, should_wake: bool) -> dict[str, list[GoldLabel]]:
    grouped: dict[str, list[GoldLabel]] = {}
    for label in labels:
        if label.should_wake is should_wake:
            grouped.setdefault(label.watch_id, []).append(label)
    return grouped


def setup_examples(
    watch_id: str,
    labels: dict[str, list[GoldLabel]],
    events: dict[str, EmailEvent],
    limit: int = 5,
) -> list[dict[str, Any]]:
    examples = []
    for label in labels.get(watch_id, [])[:limit]:
        event = events.get(label.event_id)
        if not event:
            continue
        examples.append(
            {
                "event_id": event.event_id,
                "from_email": event.from_email,
                "to": event.to,
                "subject": event.subject,
                "body": event.body,
                "reason": label.reason,
            }
        )
    return examples
