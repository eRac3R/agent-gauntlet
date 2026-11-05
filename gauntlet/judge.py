"""LLM judges for DeepEval, provider-neutral.

LocalJudge talks to any OpenAI-compatible endpoint (Ollama by default; free, local,
no account). If no endpoint is reachable, OfflineJudge is used so the deterministic
metrics still run for free.
"""
from __future__ import annotations

import functools
import json

from deepeval.models import DeepEvalBaseLLM

from app.llm import LLMClient


class OfflineJudge(DeepEvalBaseLLM):
    """Placeholder model: lets DeepEval metrics that need no LLM be constructed offline."""

    def __init__(self):
        pass

    def load_model(self):
        return None

    def generate(self, prompt: str, schema=None):
        raise RuntimeError("OfflineJudge cannot judge. Start a local model (e.g. Ollama) to enable LLM-as-judge metrics.")

    async def a_generate(self, prompt: str, schema=None):
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return "offline-stub"


class LocalJudge(DeepEvalBaseLLM):
    """Any OpenAI-compatible model as the DeepEval judge (custom model pattern)."""

    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()

    def load_model(self):
        return self.client

    @staticmethod
    def _prompt(prompt: str, schema) -> str:
        if schema is None:
            return prompt
        return f"{prompt}\n\nReturn ONLY valid JSON matching this schema:\n{json.dumps(schema.model_json_schema())}"

    @staticmethod
    def _parse(text: str, schema):
        if schema is None:
            return text
        start, end = text.find("{"), text.rfind("}")
        return schema.model_validate_json(text[start : end + 1])

    def generate(self, prompt: str, schema=None):
        msg = self.client.chat([{"role": "user", "content": self._prompt(prompt, schema)}], max_tokens=1024)
        return self._parse(msg.get("content") or "", schema)

    async def a_generate(self, prompt: str, schema=None):
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return self.client.model


@functools.lru_cache(maxsize=1)
def judge_available() -> bool:
    return LLMClient().reachable()


def get_judge() -> DeepEvalBaseLLM:
    return LocalJudge() if judge_available() else OfflineJudge()
