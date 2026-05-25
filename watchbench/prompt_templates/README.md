# Evaluation Prompt Templates

These prompts define the LLM-facing adapter boundary used by the public
evaluator.

- `eval/polling_agent_tick.md`: generic timer-based inbox-monitoring baseline.
- `eval/openclaw_polling_tick.md`: OpenClaw polling baseline.
- `eval/watchline_setup_reply.md`: optional setup-answer helper for Watchline API runs.
- `eval/watchline_delivery_openclaw.md`: downstream OpenClaw handling for matched Watchline deliveries.

The evaluator renders templates with Python `string.Template`.
