# WatchBench Email V0 Mini

This is a compact email-stream benchmark sample for WatchBench.

## Scope

- One stream equals one user's inbox over time.
- Five natural but resolved watches run over the same stream.
- Every email event is labeled against every watch.
- Labels are binary: `should_wake`.

## Counts

- Events: 100
- Watches: 5
- Labels: 500
- Positive labels: 77

## Intended Use

Use this mini sample for quick evaluator smoke tests and adapter development.
It follows the same schema as the full dataset.
