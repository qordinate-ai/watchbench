"""Provider-neutral JSON LLM clients for evaluator adapters."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
MAX_ATTEMPTS = 4
JSON_SYSTEM_PROMPT = "Return valid JSON only. Do not include markdown fences, explanations, or comments."


@dataclass(frozen=True)
class LLMResult:
    parsed: Any
    usage: dict[str, Any]


class JsonLLMClient(Protocol):
    provider: str
    model: str

    def complete_json(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        call_name: str,
    ) -> LLMResult:
        ...


def default_model(provider: str) -> str:
    if provider == "anthropic":
        return DEFAULT_ANTHROPIC_MODEL
    if provider == "openai":
        return DEFAULT_OPENAI_MODEL
    raise ValueError(f"Unknown LLM provider: {provider}")


def make_json_llm_client(*, provider: str, model: str | None = None) -> JsonLLMClient:
    chosen_model = model or default_model(provider)
    if provider == "anthropic":
        return AnthropicJsonClient(model=chosen_model)
    if provider == "openai":
        return OpenAIJsonClient(model=chosen_model)
    raise ValueError(f"Unknown LLM provider: {provider}")


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required. Run through: zsh -lc 'source ~/.zshrc && ...'")
    return value


def parse_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start_obj = cleaned.find("{")
        start_arr = cleaned.find("[")
        starts = [pos for pos in [start_obj, start_arr] if pos != -1]
        if not starts:
            raise
        start = min(starts)
        decoder = json.JSONDecoder()
        parsed, _ = decoder.raw_decode(cleaned[start:])
        return parsed


def post_json(
    *,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    call_name: str,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(
            url,
            data=body,
            headers={"content-type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            if exc.code < 500 or attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"{call_name} HTTP {exc.code}: {error_body[:2000]}") from exc
            last_error = RuntimeError(f"HTTP {exc.code}: {error_body[:2000]}")
        except (ConnectionResetError, OSError, URLError, json.JSONDecodeError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"{call_name} failed: {exc}") from exc
            last_error = exc
        time.sleep(2 * attempt)
    raise RuntimeError(f"{call_name} failed unexpectedly: {last_error}")


class AnthropicJsonClient:
    provider = "anthropic"

    def __init__(self, *, model: str = DEFAULT_ANTHROPIC_MODEL) -> None:
        self.model = model

    def complete_json(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        call_name: str,
    ) -> LLMResult:
        data = post_json(
            url=ANTHROPIC_URL,
            payload={
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": JSON_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
            headers={
                "x-api-key": require_env("ANTHROPIC_API_KEY"),
                "anthropic-version": "2023-06-01",
            },
            call_name=call_name,
        )
        text = "\n".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        ).strip()
        return LLMResult(parsed=parse_json(text), usage=data.get("usage", {}))


class OpenAIJsonClient:
    provider = "openai"

    def __init__(self, *, model: str = DEFAULT_OPENAI_MODEL) -> None:
        self.model = model

    def complete_json(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        call_name: str,
    ) -> LLMResult:
        data = post_json(
            url=OPENAI_CHAT_COMPLETIONS_URL,
            payload={
                "model": self.model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": JSON_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            },
            headers={"authorization": f"Bearer {require_env('OPENAI_API_KEY')}"},
            call_name=call_name,
        )
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"{call_name} returned no OpenAI choices")
        content = choices[0].get("message", {}).get("content", "")
        return LLMResult(parsed=parse_json(content), usage=normalize_openai_usage(data.get("usage", {})))


def normalize_openai_usage(usage: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }
