"""Small JSON-over-HTTP helper for benchmark adapters."""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any
from urllib.error import HTTPError, URLError

MAX_ATTEMPTS = 4


def post_json(
    *,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request_headers = {"content-type": "application/json", **(headers or {})}
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            if exc.code < 500 or attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"POST {url} returned HTTP {exc.code}: {error_body[:2000]}") from exc
            last_error = RuntimeError(f"HTTP {exc.code}: {error_body[:2000]}")
        except (ConnectionResetError, OSError, URLError, json.JSONDecodeError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"POST {url} failed: {exc}") from exc
            last_error = exc
        time.sleep(2 * attempt)
    raise RuntimeError(f"POST {url} failed unexpectedly: {last_error}")
