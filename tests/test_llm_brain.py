"""LLMBrain against a fake OpenAI-compatible server: proves the wire format with no real model."""
import json

import httpx

from app.agent import run_agent
from app.brains import LLMBrain
from app.llm import LLMClient
from app.models import FaultKind, FaultSpec


def fake_server(seen):
    """Pretend model: calls get_order first; after a failed tool result, calls web_search; then answers."""
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        tool_msgs = [m for m in body["messages"] if m["role"] == "tool"]
        usage = {"prompt_tokens": 50, "completion_tokens": 10}
        if not tool_msgs:
            call = {"id": "c1", "type": "function", "function": {"name": "get_order", "arguments": '{"order_id": "O-5001"}'}}
        elif len(tool_msgs) == 1:
            call = {"id": "c2", "type": "function", "function": {"name": "web_search", "arguments": '{"query": "order status"}'}}
        else:
            msg = {"role": "assistant", "content": "General guidance: orders ship in 2 business days."}
            return httpx.Response(200, json={"choices": [{"message": msg}], "usage": usage})
        msg = {"role": "assistant", "content": None, "tool_calls": [call]}
        return httpx.Response(200, json={"choices": [{"message": msg}], "usage": usage})
    return handler


def test_llm_brain_runs_through_the_agent_loop():
    seen: list[dict] = []
    client = LLMClient(base_url="http://fake/v1", model="fake", transport=httpx.MockTransport(fake_server(seen)))
    traj = run_agent("Where is order O-5001?", LLMBrain(client), FaultSpec(tool="get_order", kind=FaultKind.error))
    assert traj.path == ["get_order", "web_search"]
    assert "general guidance" in traj.answer.lower()
    assert traj.tokens_in == 150 and traj.tokens_out == 30  # real usage from the endpoint is used
    assert seen[0]["tools"][0]["type"] == "function"          # OpenAI tool format
    assert seen[-1]["messages"][-1]["role"] == "tool"         # tool results sent back


def test_client_waits_and_retries_on_rate_limit():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

    client = LLMClient(base_url="http://fake/v1", model="fake", transport=httpx.MockTransport(handler))
    assert client.chat([{"role": "user", "content": "hi"}])["content"] == "ok"
    assert len(calls) == 3
