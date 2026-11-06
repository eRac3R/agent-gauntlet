"""Provider-neutral LLM client for any OpenAI-compatible chat endpoint.

Works with, for example:
  - Ollama (local, free, no account):  http://localhost:11434/v1   (default)
  - LM Studio / llama.cpp server:      http://localhost:1234/v1
  - Groq / OpenRouter / Gemini free tiers: set the base URL and API key below

Configure with environment variables (no vendor lock-in, no required account):
  GAUNTLET_LLM_BASE_URL   default http://localhost:11434/v1
  GAUNTLET_LLM_MODEL      default llama3.2
  GAUNTLET_LLM_API_KEY    optional; local servers ignore it
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.2"


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 120.0,
        retries: int = 4,
    ):
        self.retries = retries
        self.base_url = (base_url or os.getenv("GAUNTLET_LLM_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.model = model or os.getenv("GAUNTLET_LLM_MODEL", DEFAULT_MODEL)
        key = api_key or os.getenv("GAUNTLET_LLM_API_KEY", "")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        self.http = httpx.Client(base_url=self.base_url, headers=headers, transport=transport, timeout=timeout)

    def chat(self, messages: list[dict[str, Any]], tools: list[dict] | None = None, max_tokens: int = 512) -> dict:
        """Returns the first choice's message plus a `usage` entry."""
        body: dict[str, Any] = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": 0}
        if tools:
            body["tools"] = tools
        for attempt in range(self.retries + 1):
            resp = self.http.post("/chat/completions", json=body)
            if resp.status_code != 429 or attempt == self.retries:
                break
            # Free tiers rate-limit per minute: honour Retry-After, capped so a run cannot hang.
            time.sleep(min(float(resp.headers.get("retry-after") or 2 ** attempt), 20.0))
        resp.raise_for_status()
        data = resp.json()
        return {**data["choices"][0]["message"], "usage": data.get("usage") or {}}

    def reachable(self) -> bool:
        try:
            return self.http.get("/models", timeout=2.0).status_code < 500
        except httpx.HTTPError:
            return False


def endpoint_available() -> bool:
    return LLMClient().reachable()


def to_openai_tools(schemas: list[dict]) -> list[dict]:
    return [
        {"type": "function", "function": {"name": s["name"], "description": s["description"], "parameters": s["input_schema"]}}
        for s in schemas
    ]
