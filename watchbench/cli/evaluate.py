#!/usr/bin/env python3
"""Run WatchBench candidate adapters against an email dataset."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from watchbench.adapters.oracle import OracleAdapter
from watchbench.adapters.openclaw_polling import (
    OpenClawConfig,
    OpenClawParallelPollingAdapter,
    OpenClawPollingAdapter,
)
from watchbench.adapters.polling_agent import PollingAgentAdapter
from watchbench.adapters.watchline_api import WatchlineApiAdapter
from watchbench.dataset import load_dataset
from watchbench.llm import default_model, make_json_llm_client
from watchbench.runner import run_candidate, subset_dataset
from watchbench.types import CandidateWake

DEFAULT_WATCHLINE_API_BASE_URL = "https://api.watch.qordinate.ai"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/watchbench-email-v0-mini")
    parser.add_argument(
        "--candidate",
        action="append",
        choices=[
            "gold-oracle",
            "watchline-api",
            "generic-llm-polling-agent",
            "openclaw-polling-agent",
            "openclaw-parallel-polling-agent",
        ],
        required=True,
        help="Candidate to run. Pass more than once to compare multiple candidates.",
    )
    parser.add_argument("--llm-provider", choices=["anthropic", "openai"], default="anthropic")
    parser.add_argument("--model", default=None, help="Provider model. Defaults by --llm-provider.")
    parser.add_argument("--poll-minutes", type=int, default=15)
    parser.add_argument("--max-events", type=int)
    parser.add_argument("--max-watches", type=int)
    parser.add_argument("--watch-id", action="append", default=[])
    parser.add_argument("--metadata-limit", type=int)
    parser.add_argument("--watchline-api-key", default=os.environ.get("WATCHLINE_API_KEY", ""))
    parser.add_argument("--watchline-channel-id", default=os.environ.get("WATCHLINE_CHANNEL_ID", ""))
    parser.add_argument("--watchline-user-id", default="")
    parser.add_argument("--watchline-openclaw-session-id", default="")
    parser.add_argument("--openclaw-session-id", default="")
    parser.add_argument("--openclaw-model", default=None)
    parser.add_argument("--openclaw-thinking", default="low")
    parser.add_argument("--openclaw-timeout-seconds", type=int, default=600)
    parser.add_argument("--openclaw-parallelism", type=int, default=8)
    parser.add_argument("--openclaw-local", action="store_true")
    parser.add_argument("--output", default="")
    return parser.parse_args()


def build_adapter(
    name: str,
    *,
    args: argparse.Namespace,
    llm_provider: str,
    model: str,
    metadata_limit: int | None,
):
    if name == "gold-oracle":
        return OracleAdapter()
    if name == "watchline-api":
        require_arg(args.watchline_api_key, "--watchline-api-key or WATCHLINE_API_KEY")
        require_arg(args.watchline_channel_id, "--watchline-channel-id or WATCHLINE_CHANNEL_ID")
        return WatchlineApiAdapter(
            api_base_url=DEFAULT_WATCHLINE_API_BASE_URL,
            api_key=args.watchline_api_key,
            channel_id=args.watchline_channel_id,
            user_id=args.watchline_user_id or default_watchline_user_id(),
            setup_responder=make_json_llm_client(provider=llm_provider, model=model),
            downstream_openclaw=(
                OpenClawConfig(
                    session_id=args.watchline_openclaw_session_id,
                    model=args.openclaw_model,
                    thinking=args.openclaw_thinking,
                    timeout_seconds=args.openclaw_timeout_seconds,
                    local=args.openclaw_local,
                )
                if args.watchline_openclaw_session_id
                else None
            ),
        )
    if name == "openclaw-polling-agent":
        return OpenClawPollingAdapter(
            config=OpenClawConfig(
                session_id=args.openclaw_session_id or default_openclaw_session_id(),
                model=args.openclaw_model,
                thinking=args.openclaw_thinking,
                timeout_seconds=args.openclaw_timeout_seconds,
                local=args.openclaw_local,
            ),
            metadata_limit=metadata_limit,
        )
    if name == "openclaw-parallel-polling-agent":
        return OpenClawParallelPollingAdapter(
            config=OpenClawConfig(
                session_id=args.openclaw_session_id or default_openclaw_session_id(),
                model=args.openclaw_model,
                thinking=args.openclaw_thinking,
                timeout_seconds=args.openclaw_timeout_seconds,
                local=args.openclaw_local,
            ),
            metadata_limit=metadata_limit,
            max_workers=args.openclaw_parallelism,
        )
    llm = make_json_llm_client(provider=llm_provider, model=model)
    if name == "generic-llm-polling-agent":
        return PollingAgentAdapter(llm=llm, metadata_limit=metadata_limit)
    raise ValueError(f"Unknown candidate: {name}")


def require_arg(value: str, name: str) -> None:
    if not value:
        raise SystemExit(f"{name} is required for --candidate watchline-api")


def default_watchline_user_id() -> str:
    return f"watchbench_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def default_openclaw_session_id() -> str:
    return f"watchbench-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def wake_to_dict(wake: CandidateWake) -> dict[str, Any]:
    row = asdict(wake)
    row["wake_time"] = wake.wake_time.isoformat()
    return row


def default_output_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("results") / f"watchbench_eval_{stamp}.json"


def main() -> int:
    args = parse_args()
    dataset = subset_dataset(
        load_dataset(Path(args.dataset)),
        max_events=args.max_events,
        max_watches=args.max_watches,
        watch_ids=set(args.watch_id) if args.watch_id else None,
    )
    output = Path(args.output) if args.output else default_output_path()
    output.parent.mkdir(parents=True, exist_ok=True)

    runs = []
    model = args.model or default_model(args.llm_provider)
    for candidate_name in args.candidate:
        adapter = build_adapter(
            candidate_name,
            args=args,
            llm_provider=args.llm_provider,
            model=model,
            metadata_limit=args.metadata_limit,
        )
        score, wakes = run_candidate(
            dataset=dataset,
            adapter=adapter,
            poll_interval=timedelta(minutes=args.poll_minutes),
        )
        runs.append(
            {
                "candidate": candidate_name,
                "metrics": score.metrics,
                "wakes": [wake_to_dict(wake) for wake in wakes],
            }
        )

    payload = {
        "dataset": dataset.name,
        "event_count": len(dataset.events),
        "watch_count": len(dataset.watches),
        "label_count": len(dataset.labels),
        "poll_minutes": args.poll_minutes,
        "runs": runs,
    }
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(output), "runs": [run["metrics"] for run in runs]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
