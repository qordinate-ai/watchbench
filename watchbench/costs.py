"""Cost accounting primitives for candidate runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CostLedger:
    """Tracks source reads and model usage in one place.

    Candidate adapters should not maintain their own counters. Keeping this
    centralized makes OpenClaw/Hermes/Watchline adapters comparable even though
    they will call very different runtime APIs later.
    """

    source_list_calls: int = 0
    source_search_calls: int = 0
    source_get_calls: int = 0
    source_metadata_returned: int = 0
    source_bodies_returned: int = 0
    llm_calls: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    notes: list[str] = field(default_factory=list)

    def record_llm_usage(self, usage: dict[str, Any] | None) -> None:
        self.llm_calls += 1
        if not usage:
            return
        self.llm_input_tokens += int(usage.get("input_tokens", 0) or 0)
        self.llm_output_tokens += int(usage.get("output_tokens", 0) or 0)

    def as_dict(self) -> dict[str, Any]:
        useful_source_calls = self.source_list_calls + self.source_search_calls + self.source_get_calls
        return {
            "source_list_calls": self.source_list_calls,
            "source_search_calls": self.source_search_calls,
            "source_get_calls": self.source_get_calls,
            "source_calls_total": useful_source_calls,
            "source_metadata_returned": self.source_metadata_returned,
            "source_bodies_returned": self.source_bodies_returned,
            "llm_calls": self.llm_calls,
            "llm_input_tokens": self.llm_input_tokens,
            "llm_output_tokens": self.llm_output_tokens,
            "llm_tokens_total": self.llm_input_tokens + self.llm_output_tokens,
            "notes": self.notes,
        }
