# WatchBench

WatchBench evaluates intent-defined event routing for agents. It asks a narrow,
practical question:

> Given a noisy source-event stream and a set of explicit user watches, which
> events should wake the downstream agent?

The first dataset, `watchbench-email-v0`, is an email-stream benchmark for
comparing event routing systems, polling agents, and oracle sanity checks on the
same inbox stream.

## What Is Included

- `data/watchbench-email-v0-full/`: 500 synthetic email events, 20 resolved
  watch intents, and 10,000 binary watch-event labels.
- `data/watchbench-email-v0-mini/`: a smaller copy for quick smoke tests.
- `watchbench/`: dataset loading, virtual inbox replay, candidate adapters,
  scoring, cost accounting, and CLI entrypoints.
- `scripts/`: thin compatibility wrappers for the package CLIs.
- `hf/`: Hugging Face-friendly export files and dataset card.
- `results/`: canonical JSON outputs used by the public report.
- `reports/email_v0_full_slice_comparison.md`: the current substantive runtime
  comparison.

## Metrics

The evaluator replays events in chronological order and scores emitted wakes
against the gold labels.

- `precision`: delivered wakes that were correct.
- `recall`: gold-positive watch-event pairs that were delivered.
- `f1`: harmonic mean of precision and recall.
- `source calls`: source-list/search/get calls made by a candidate.
- `agent calls`: downstream agent or LLM invocations made by a candidate.
- `agent tokens`: downstream agent or LLM token usage reported by the candidate.
- `latency`: time from source event occurrence to delivered wake.
- `duplicate wakes`: repeated wakes for the same watch-event pair.

## Quick Start

Use Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run the deterministic oracle on a small slice:

```bash
watchbench-evaluate \
  --dataset data/watchbench-email-v0-mini \
  --candidate gold-oracle \
  --max-events 20 \
  --output /tmp/watchbench_eval_oracle_smoke.json
```

Run the oracle on the canonical reported slice:

```bash
watchbench-evaluate \
  --dataset data/watchbench-email-v0-full \
  --candidate gold-oracle \
  --max-events 50 \
  --max-watches 5 \
  --poll-minutes 60 \
  --output results/oracle_full_slice_50x5.json
```

## Candidate Adapters

`gold-oracle` uses labels directly. It is a scorer sanity check, not a real
baseline.

`generic-llm-polling-agent` simulates a timer-based inbox agent. On each tick it
lists new emails, fetches full bodies, and asks an LLM which watches should
wake. Use `--llm-provider anthropic` with `ANTHROPIC_API_KEY`, or
`--llm-provider openai` with `OPENAI_API_KEY`.

`openclaw-polling-agent` and `openclaw-parallel-polling-agent` invoke the real
`openclaw agent --json` CLI on each polling tick and record token usage returned
by the CLI.

`watchline-api` creates watches through the hosted Watchline API at
`https://api.watch.qordinate.ai`, ingests benchmark events, polls pull
deliveries, and optionally hands matched deliveries to
OpenClaw so downstream agent cost is counted.

Example Watchline API run:

```bash
WATCHLINE_API_KEY=wl_example_public_benchmark_key \
WATCHLINE_CHANNEL_ID=ch_example_public_benchmark_channel \
watchbench-evaluate \
  --dataset data/watchbench-email-v0-full \
  --candidate watchline-api \
  --max-events 50 \
  --max-watches 5 \
  --poll-minutes 60 \
  --watchline-user-id watchbench_public_eval \
  --output results/watchline_eval_50x5.json
```

## Current Report

The current 50-event x 5-watch comparison reports:

- Watchline reduced source calls by `68.2%` versus OpenClaw polling.
- Watchline reduced downstream agent tokens by `91.0%`.
- The reported cost surface is downstream agent cost and source-app access cost.

See `reports/email_v0_full_slice_comparison.md` for the exact numbers and
measurement boundary.

## Dataset Files

Each dataset directory contains:

- `stream.json`: stream/user metadata.
- `events.jsonl`: chronological email events.
- `watches.jsonl`: resolved natural-language watch intents.
- `labels.jsonl`: one binary label for every watch-event pair.
- `manifest.json`: dataset counts and metadata.
- `dataset_card.md`: scope, counts, and limitations.

The core label shape is:

```json
{
  "watch_id": "watch_001",
  "event_id": "email_0001",
  "should_wake": true,
  "reason": "The email satisfies the watch condition."
}
```

## Hugging Face Export

The `hf/` directory contains denormalized `pairs.jsonl` files for dataset
viewer and `load_dataset` workflows. Regenerate them with:

```bash
watchbench-export-hf
```

Each pair row joins one watch, one email event, and its label.
