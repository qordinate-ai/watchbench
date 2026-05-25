---
license: mit
language:
  - en
pretty_name: WatchBench Email V0
tags:
  - agents
  - email
  - benchmark
  - event-routing
  - jsonl
configs:
  - config_name: full_pairs
    data_files:
      - split: test
        path: full/pairs.jsonl
  - config_name: mini_pairs
    data_files:
      - split: test
        path: mini/pairs.jsonl
  - config_name: full_events
    data_files:
      - split: test
        path: full/events.jsonl
  - config_name: full_watches
    data_files:
      - split: test
        path: full/watches.jsonl
  - config_name: full_labels
    data_files:
      - split: test
        path: full/labels.jsonl
  - config_name: mini_events
    data_files:
      - split: test
        path: mini/events.jsonl
  - config_name: mini_watches
    data_files:
      - split: test
        path: mini/watches.jsonl
  - config_name: mini_labels
    data_files:
      - split: test
        path: mini/labels.jsonl
---

# WatchBench Email V0

WatchBench evaluates intent-defined event routing for agents. Given a noisy
email stream and explicit user watches, the task is to decide which emails
should wake the downstream agent.

## Configs

- `full_pairs`: denormalized watch-event rows for the full dataset.
- `mini_pairs`: denormalized watch-event rows for quick inspection.
- `full_events`: event-only rows for the full stream.
- `mini_events`: event-only rows for the mini stream.
- `full_watches` and `mini_watches`: watch intent rows.
- `full_labels` and `mini_labels`: binary watch-event labels.

The benchmark repository also includes relational files for replay:
`events.jsonl`, `watches.jsonl`, `labels.jsonl`, and `manifest.json`.

## Pair Row Schema

Each `pairs.jsonl` row contains:

- `watch_id` and `watch_intent`
- `event_id`, timestamp, sender, recipients, subject, body, and attachments
- `should_wake`
- `reason`

## Counts

| Split | Events | Watches | Pairs | Positive pairs |
| --- | ---: | ---: | ---: | ---: |
| full | 500 | 20 | 10,000 | 412 |
| mini | 100 | 5 | 500 | 77 |

## Use

```python
from datasets import load_dataset

dataset = load_dataset("watchline/watchbench-email-v0", "full_pairs", split="test")
```

## License

MIT.
