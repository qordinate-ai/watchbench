"""Prompt rendering helpers for evaluator adapters."""

from __future__ import annotations

from importlib import resources
from string import Template
from typing import Any

PROMPT_PACKAGE = "watchbench"
PROMPT_ROOT = "prompt_templates"


def render_prompt(relative_path: str, **values: Any) -> str:
    template_path = resources.files(PROMPT_PACKAGE).joinpath(PROMPT_ROOT, relative_path)
    template = Template(template_path.read_text(encoding="utf-8"))
    return template.substitute({key: str(value) for key, value in values.items()}).strip()
