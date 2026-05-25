# Email V0 Full Slice Comparison

Generated: 2026-05-21 14:41 IST

Dataset: `data/watchbench-email-v0-full/`  
Watchline result: `results/watchline_50x5_downstream_openclaw.json`  
OpenClaw result: `results/openclaw_parallel_50x5.json`  
Oracle sanity result: `results/oracle_full_slice_50x5.json`

## Dataset

The full dataset has:

- 1 inbox stream.
- 500 chronological email events.
- 20 fully resolved watch intents.
- 10,000 watch-event labels.
- 412 positive labels.

Labels were reviewed for consistency and are included so runs can be reproduced
and compared.

## Runtime Slice

The latest substantive runtime comparison used the first 50 events and first 5
watches from the full dataset:

- 250 watch-event pairs.
- 19 gold-positive pairs.
- 60-minute simulated polling/pull ticks.

The harness advances benchmark time instantly; it does not sleep for 60 real
minutes. A tick represents "what each candidate would see at that minute mark."

## Candidates

`watchline-api` used the hosted Watchline API at `https://api.watch.qordinate.ai`:

- created real watches,
- continued setup when Watchline asked for more precise filter criteria,
- pushed events through `/v1/events.ingest`,
- polled pull deliveries,
- acked deliveries,
- passed each matched delivery to a real OpenClaw session and counted that
  downstream OpenClaw token usage.

The measured cost surface is downstream agent cost and source-app event access
cost. Watchline service-side matching cost is outside this benchmark surface.

`openclaw-parallel-polling-agent` used real OpenClaw sessions on each polling
tick:

- listed newly visible messages,
- fetched email bodies,
- asked OpenClaw to decide which watches should wake,
- counted OpenClaw token usage returned by the CLI;
- ran independent polling ticks concurrently so the benchmark does not wait on
  wall-clock serialization.

## Results

| Candidate | TP | FP | FN | Precision | Recall | F1 | Source calls | Agent calls | Agent tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| watchline-api + downstream OpenClaw | 17 | 2 | 2 | 0.895 | 0.895 | 0.895 | 50 | 21 | 45,904 |
| openclaw-parallel-polling-agent | 18 | 0 | 1 | 1.000 | 0.947 | 0.973 | 157 | 42 | 508,583 |

Cost reduction from OpenClaw polling to Watchline:

- Source calls: 157 -> 50, a 68.2% reduction.
- Agent LLM calls: 42 -> 21, a 50.0% reduction.
- Agent LLM tokens: 508,583 -> 45,904, a 91.0% reduction.

Watchline's pull latency profile on true positives:

- p50: 1,380 seconds.
- p95: 3,300 seconds.
- max: 3,420 seconds.

## What This Shows

This 50-event slice shows the expected cost shape:

- Watchline read each source event once and woke only on deliveries.
- OpenClaw polling did more source work because it lists messages on each tick
  and fetches bodies for new messages.
- Watchline cut downstream OpenClaw token use by roughly an order of magnitude
  because OpenClaw only processed matched deliveries.
- The result table reports the observed precision, recall, and F1 for each
  candidate on the same slice.

## Interpretation

This is a verified substantive slice on the full dataset:

- the full dataset is now materialized and replayable;
- the scorer works on a 50-event × 5-watch slice;
- Watchline API ingest and pull delivery work against the benchmark;
- real OpenClaw polling works against the same slice;
- downstream OpenClaw delivery handling is counted for Watchline.

The measurement boundary is downstream agent cost plus source-app event access
cost. Watchline service-side matching cost is outside this benchmark surface.
