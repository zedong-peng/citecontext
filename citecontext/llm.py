"""OpenAI-compatible LLM client using only stdlib.

Supports DeepSeek R1 / V3 and other OpenAI-compatible endpoints.
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for the LLM client."""

    api_base: str
    api_key: str
    model: str
    timeout_sec: float = 300.0
    max_tokens: int = 4096
    temperature: float = 0.1


class LLMClient:
    """Minimal OpenAI-compatible chat completion client (stdlib only)."""

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send a chat completion request and return the assistant message content.

        For reasoning models (e.g. DeepSeek-R1) that return ``reasoning_content``
        alongside ``content``, only the final ``content`` is returned.
        """
        url = f"{self.cfg.api_base.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "max_tokens": max_tokens or self.cfg.max_tokens,
            "temperature": temperature if temperature is not None else self.cfg.temperature,
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cfg.api_key}",
            # Compatibility with some OpenAI-like providers / gateways
            "X-Api-Key": self.cfg.api_key,
            "api-key": self.cfg.api_key,
        }
        req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.cfg.timeout_sec) as resp:
                    body = json.loads(resp.read().decode("utf-8"))

                choices = body.get("choices") or []
                if not choices:
                    raise RuntimeError(f"LLM returned no choices: {body}")

                message = choices[0].get("message") or {}
                content = message.get("content") or ""
                return content.strip()

            except urllib.error.HTTPError as e:
                try:
                    err_body = e.read().decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    err_body = ""

                # Don't retry on auth / request errors (except 429).
                if e.code != 429 and 400 <= int(e.code) < 500:
                    raise RuntimeError(f"LLM HTTP {e.code}: {err_body or e}") from e

                if attempt >= max_retries:
                    raise RuntimeError(f"LLM HTTP {e.code} after {attempt} attempts: {err_body or e}") from e
                time.sleep(2**attempt)
            except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
                if attempt >= max_retries:
                    raise RuntimeError(f"LLM request failed after {attempt} attempts: {e}") from e
                time.sleep(2**attempt)

        raise RuntimeError("LLM request failed: exhausted retries")  # unreachable
