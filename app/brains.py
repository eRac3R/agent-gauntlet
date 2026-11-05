"""Decision policies ("brains") the agent loop can run.

Scripted brains are deterministic stand-ins with deliberately different failure
behaviour, so the eval suite has real regressions to catch at zero API cost.
LLMBrain is a real model behind any OpenAI-compatible endpoint (local Ollama by default).
"""
from __future__ import annotations

import json

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.models import Step
from app.llm import LLMClient, to_openai_tools
from app.tools import TOOL_SCHEMAS

CUST_RE = re.compile(r"C-\d{4}")
ORD_RE = re.compile(r"O-\d{4}")

SCRIPTED_AGENTS = {
    "naive": "Retries the exact same failing call forever (v1 that only passes happy paths).",
    "resilient": "Retries timeouts once, then falls back to web search (the good baseline).",
    "wasteful": "Always web-searches first, then does the real work (extra steps and tokens).",
}


@dataclass
class Action:
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    final: str | None = None
    success: bool = True
    usage: tuple[int, int] | None = None  # (tokens_in, tokens_out) when the brain knows


class Brain(Protocol):
    name: str

    def decide(self, query: str, steps: list[Step]) -> Action: ...


def _compose_answer(query: str, steps: list[Step]) -> Action:
    ok: dict[str, Step] = {s.tool: s for s in steps if s.status == "ok"}
    parts: list[str] = []
    if "lookup_customer" in ok:
        c = json.loads(ok["lookup_customer"].output)
        parts.append(f"Customer {c['name']} ({c['email']}) is on the {c['plan']} plan.")
    if "get_order" in ok:
        o = json.loads(ok["get_order"].output)
        parts.append(f"Order {o['id']} is {o['status']}.")

    web = json.loads(ok["web_search"].output)[0] if "web_search" in ok else None
    degraded = any(s.status != "ok" for s in steps) and web is not None
    has_ids = bool(CUST_RE.search(query) or ORD_RE.search(query))

    if parts and degraded:
        return Action(final=" ".join(parts) + f" Note: partial data; general guidance: {web}")
    if parts:
        return Action(final=" ".join(parts))
    if web and has_ids:
        return Action(final=f"I couldn't reach the account system, so here is general guidance: {web}")
    if web:
        return Action(final=web)
    return Action(final="Sorry, I couldn't complete this request.", success=False)


class ScriptedBrain:
    def __init__(self, style: str):
        if style not in SCRIPTED_AGENTS:
            raise ValueError(f"unknown scripted agent {style!r}")
        self.name = style

    def decide(self, query: str, steps: list[Step]) -> Action:
        needs: list[tuple[str, dict[str, Any]]] = []
        if m := CUST_RE.search(query):
            needs.append(("lookup_customer", {"customer_id": m.group()}))
        if m := ORD_RE.search(query):
            needs.append(("get_order", {"order_id": m.group()}))
        if not needs:
            needs.append(("web_search", {"query": query}))

        if self.name == "wasteful" and not steps:
            return Action(tool="web_search", args={"query": query})

        last = steps[-1] if steps else None
        if last is not None and last.status != "ok":
            return self._on_failure(query, steps, last)

        done = {s.tool for s in steps if s.status == "ok"}
        if any(s.status != "ok" for s in steps) and "web_search" in done:
            return _compose_answer(query, steps)
        for tool, args in needs:
            if tool not in done:
                return Action(tool=tool, args=args)
        return _compose_answer(query, steps)

    def _on_failure(self, query: str, steps: list[Step], last: Step) -> Action:
        if self.name == "naive":
            return Action(tool=last.tool, args=last.args)
        if last.tool == "web_search":
            return _compose_answer(query, steps)
        repeats = sum(1 for s in steps if s.tool == last.tool and s.args == last.args)
        if last.status == "timeout" and repeats < 2:
            return Action(tool=last.tool, args=last.args)
        if any(s.tool == "web_search" and s.status == "ok" for s in steps):
            return _compose_answer(query, steps)
        return Action(tool="web_search", args={"query": query})


SYSTEM_PROMPT = (
    "You are a customer-support agent with three tools: lookup_customer, get_order, web_search. "
    "Use the fewest tool calls needed. Never repeat an identical failing call more than once. "
    "If account tools fail or return nothing, fall back to web_search and say your answer is general guidance."
)


class LLMBrain:
    """A real model behind any OpenAI-compatible endpoint (Ollama by default). See app/llm.py."""

    name = "llm"

    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()

    def decide(self, query: str, steps: list[Step]) -> Action:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]
        for s in steps:
            tid = f"call_{s.index}"
            messages.append({
                "role": "assistant", "content": None,
                "tool_calls": [{"id": tid, "type": "function", "function": {"name": s.tool, "arguments": json.dumps(s.args)}}],
            })
            messages.append({"role": "tool", "tool_call_id": tid, "content": s.output})

        msg = self.client.chat(messages, tools=to_openai_tools(TOOL_SCHEMAS))
        u = msg.get("usage", {})
        usage = (u["prompt_tokens"], u["completion_tokens"]) if "prompt_tokens" in u else None

        for call in msg.get("tool_calls") or []:
            fn = call["function"]
            args = fn["arguments"]
            try:
                args = json.loads(args) if isinstance(args, str) else dict(args)
            except json.JSONDecodeError:
                args = {}
            return Action(tool=fn["name"], args=args, usage=usage)
        text = (msg.get("content") or "").strip()
        return Action(final=text or "No answer.", success=bool(text), usage=usage)


def make_brain(name: str) -> Brain:
    if name in SCRIPTED_AGENTS:
        return ScriptedBrain(name)
    if name == "llm":
        return LLMBrain()
    raise ValueError(f"unknown agent {name!r}; choose from {[*SCRIPTED_AGENTS, 'llm']}")


def list_agents() -> dict[str, str]:
    return {**SCRIPTED_AGENTS, "llm": "A real model via any OpenAI-compatible endpoint (Ollama by default, free)."}
