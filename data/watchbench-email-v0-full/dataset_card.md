# WatchBench Email V0 Full

This is an email-stream benchmark dataset for Watchline-style event
routing.

## Scope

- One stream equals one user's inbox over time.
- Natural but fully resolved watches run over the same stream.
- Every email event is labeled against every watch.
- Labels are binary: `should_wake`.

## Counts

- Events: 500
- Watches: 20
- Labels: 10000
- Positive labels: 412
- Positive label rate: 0.041

## Dataset Note

Labels were reviewed for consistency and are included so runs can be reproduced
and compared.

## Intended Use

Use this dataset to compare event layers and polling/heartbeat agents
on precision, recall, wake latency, source reads, downstream agent
calls, and duplicate wakes.
