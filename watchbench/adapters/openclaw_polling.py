"""Adapter that invokes the real OpenClaw CLI on each polling tick."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime

from watchbench.costs import CostLedger
from watchbench.inbox import VirtualInbox
from watchbench.llm import parse_json
from watchbench.prompts import render_prompt
from watchbench.types import CandidateWake, Dataset, EmailEvent, Watch


@dataclass(frozen=True)
class OpenClawConfig:
    session_id: str
    model: str | None = None
    thinking: str | None = "low"
    timeout_seconds: int = 600
    local: bool = False


class OpenClawPollingAdapter:
    """Models the native OpenClaw path as periodic agent invocations.

    Each tick sends the new emails since the previous tick to `openclaw agent`.
    This is intentionally not the Watchline plugin path. It measures the cost
    and behavior of asking the agent itself to inspect a noisy stream on a
    schedule.
    """

    name = "openclaw-polling-agent"

    def __init__(self, *, config: OpenClawConfig, metadata_limit: int | None = None) -> None:
        self._config = config
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
        self._cost.notes.append(f"openclaw_session_id={self._config.session_id}")

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
            "eval/openclaw_polling_tick.md",
            stream_user_json=json.dumps(self._stream.get("user", {}), ensure_ascii=False, indent=2),
            watches_json=json.dumps([watch.__dict__ for watch in self._watches], ensure_ascii=False, indent=2),
            events_json=json.dumps(full_events, ensure_ascii=False, indent=2),
        )
        parsed, usage = invoke_openclaw_json(prompt, self._config)
        self._cost.record_llm_usage(usage)
        if not isinstance(parsed, list):
            raise RuntimeError(f"Bad OpenClaw polling result: {parsed}")
        self._record_wakes(parsed, visible_event_ids={row["event_id"] for row in metadata_rows})

    def flush(self) -> list[CandidateWake]:
        return list(self._wakes)

    def teardown(self) -> None:
        return

    def _record_wakes(self, rows: list[dict], *, visible_event_ids: set[str]) -> None:
        valid_watch_ids = {watch.watch_id for watch in self._watches}
        for row in rows:
            if not row.get("should_wake", True):
                continue
            watch_id = row.get("watch_id")
            event_id = row.get("event_id")
            if watch_id not in valid_watch_ids or event_id not in visible_event_ids:
                raise RuntimeError(f"OpenClaw returned out-of-scope wake: {row}")
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


@dataclass(frozen=True)
class OpenClawTickWindow:
    index: int
    wake_time: datetime
    visible_event_ids: set[str]
    prompt: str


class OpenClawParallelPollingAdapter:
    """Runs the same polling prompts as OpenClawPollingAdapter in parallel.

    The cost model stays identical: one OpenClaw invocation per non-empty poll
    tick, and each invocation sees all watches plus only the emails that arrived
    since the previous tick. The only difference is execution scheduling. The
    benchmark can finish faster because tick windows are self-contained once the
    virtual inbox has recorded which emails were visible in each window.
    """

    name = "openclaw-parallel-polling-agent"

    def __init__(
        self,
        *,
        config: OpenClawConfig,
        metadata_limit: int | None = None,
        max_workers: int = 8,
    ) -> None:
        self._config = config
        self._metadata_limit = metadata_limit
        self._max_workers = max(1, max_workers)

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
        self._windows: list[OpenClawTickWindow] = []
        self._wakes: list[CandidateWake] = []
        self._seen_wakes: set[tuple[str, str]] = set()
        self._cost.notes.append(f"openclaw_session_id={self._config.session_id}")
        self._cost.notes.append(f"openclaw_parallel_workers={self._max_workers}")

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
            "eval/openclaw_polling_tick.md",
            stream_user_json=json.dumps(self._stream.get("user", {}), ensure_ascii=False, indent=2),
            watches_json=json.dumps([watch.__dict__ for watch in self._watches], ensure_ascii=False, indent=2),
            events_json=json.dumps(full_events, ensure_ascii=False, indent=2),
        )
        self._windows.append(
            OpenClawTickWindow(
                index=len(self._windows) + 1,
                wake_time=self._inbox.current_time,
                visible_event_ids={row["event_id"] for row in metadata_rows},
                prompt=prompt,
            )
        )

    def flush(self) -> list[CandidateWake]:
        if not self._windows:
            return []
        worker_count = min(self._max_workers, len(self._windows))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_window = {
                executor.submit(self._invoke_window, window): window
                for window in self._windows
            }
            for future in as_completed(future_to_window):
                window = future_to_window[future]
                parsed, usage = future.result()
                self._cost.record_llm_usage(usage)
                if not isinstance(parsed, list):
                    raise RuntimeError(f"Bad OpenClaw polling result: {parsed}")
                self._record_wakes(
                    parsed,
                    wake_time=window.wake_time,
                    visible_event_ids=window.visible_event_ids,
                )
        return list(self._wakes)

    def teardown(self) -> None:
        return

    def _invoke_window(self, window: OpenClawTickWindow):
        return invoke_openclaw_json(
            window.prompt,
            OpenClawConfig(
                session_id=f"{self._config.session_id}-tick-{window.index:04d}",
                model=self._config.model,
                thinking=self._config.thinking,
                timeout_seconds=self._config.timeout_seconds,
                local=self._config.local,
            ),
        )

    def _record_wakes(
        self,
        rows: list[dict],
        *,
        wake_time: datetime,
        visible_event_ids: set[str],
    ) -> None:
        valid_watch_ids = {watch.watch_id for watch in self._watches}
        for row in rows:
            if not row.get("should_wake", True):
                continue
            watch_id = row.get("watch_id")
            event_id = row.get("event_id")
            if watch_id not in valid_watch_ids or event_id not in visible_event_ids:
                raise RuntimeError(f"OpenClaw returned out-of-scope wake: {row}")
            key = (watch_id, event_id)
            if key in self._seen_wakes:
                continue
            self._seen_wakes.add(key)
            self._wakes.append(
                CandidateWake(
                    candidate=self.name,
                    watch_id=watch_id,
                    event_id=event_id,
                    wake_time=wake_time,
                    reason=str(row.get("reason", "")),
                )
            )


def invoke_openclaw_json(prompt: str, config: OpenClawConfig):
    args = [
        "openclaw",
        "agent",
        "--session-id",
        config.session_id,
        "--message",
        prompt,
        "--json",
        "--timeout",
        str(config.timeout_seconds),
    ]
    if config.model:
        args.extend(["--model", config.model])
    if config.thinking:
        args.extend(["--thinking", config.thinking])
    if config.local:
        args.append("--local")
    completed = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=config.timeout_seconds + 30,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "OpenClaw agent invocation failed:\n"
            f"stdout:\n{completed.stdout[-4000:]}\n"
            f"stderr:\n{completed.stderr[-4000:]}"
        )
    payload = parse_json(completed.stdout)
    text = extract_openclaw_text(payload)
    return parse_json(text), extract_openclaw_usage(payload)


def extract_openclaw_text(payload) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        payloads = payload.get("payloads")
        if isinstance(payloads, list):
            for item in payloads:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    return item["text"]
        for key in ("text", "message", "content", "reply", "output"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        for key in ("result", "data"):
            value = payload.get(key)
            if isinstance(value, (dict, str)):
                return extract_openclaw_text(value)
        for value in payload.values():
            if isinstance(value, (dict, str)):
                try:
                    return extract_openclaw_text(value)
                except RuntimeError:
                    continue
    raise RuntimeError(f"Could not find OpenClaw text output in: {payload}")


def extract_openclaw_usage(payload) -> dict:
    if not isinstance(payload, dict):
        return {}
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        result = payload.get("result")
        if isinstance(result, dict):
            return extract_openclaw_usage(result)
        return {}
    agent_meta = meta.get("agentMeta")
    if not isinstance(agent_meta, dict):
        return {}
    usage = agent_meta.get("lastCallUsage") or agent_meta.get("usage")
    if not isinstance(usage, dict):
        return {}
    return {
        "input_tokens": int(usage.get("input", 0) or 0),
        "output_tokens": int(usage.get("output", 0) or 0),
    }
