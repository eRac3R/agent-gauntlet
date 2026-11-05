from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def test_health_and_agents():
    assert client.get("/health").json() == {"status": "ok"}
    assert {"naive", "resilient", "wasteful"} <= set(client.get("/agents").json())


def test_run_returns_structured_trajectory():
    body = {"query": "Where is order O-5001?", "agent": "resilient",
            "fault": {"tool": "get_order", "kind": "error"}}
    data = client.post("/run", json=body).json()
    assert [s["tool"] for s in data["steps"]] == ["get_order", "web_search"]
    assert data["steps"][0]["status"] == "error"


def test_unknown_agent_is_404():
    assert client.post("/run", json={"query": "hi", "agent": "nope"}).status_code == 404


def test_stream_emits_steps_then_done():
    with client.stream("GET", "/run/stream", params={"query": "Where is order O-5001?", "delay": 0}) as r:
        text = "".join(r.iter_text())
    assert "event: step" in text and "event: done" in text


def test_eval_then_heatmap_and_compare():
    a = client.post("/eval", json={"agent": "resilient"}).json()
    b = client.post("/eval", json={"agent": "naive"}).json()
    assert a["pass_rate"] == 1.0 and b["pass_rate"] < 1.0
    cmp = client.get("/compare", params={"baseline": a["run_id"], "candidate": b["run_id"]}).json()
    assert cmp["regressions"]
    assert set(client.get("/heatmap").json()["agents"]) == {"resilient", "naive"}


def test_config_defaults_to_scripted_agent_without_a_model(monkeypatch):
    monkeypatch.delenv("GAUNTLET_LLM_API_KEY", raising=False)
    monkeypatch.delenv("GAUNTLET_LLM_BASE_URL", raising=False)
    assert client.get("/config").json() == {"llm_configured": False, "default_agent": "naive"}
    monkeypatch.setenv("GAUNTLET_LLM_API_KEY", "test")
    assert client.get("/config").json()["default_agent"] == "llm"


def test_rate_limit_returns_429_and_step_cap_is_enforced():
    from app import guard

    guard.reset()
    body = {"query": "Where is order O-5001?", "agent": "resilient"}
    codes = [client.post("/eval", json={"agent": "resilient", "case_ids": ["happy-01"]}).status_code for _ in range(7)]
    assert codes[:6] == [200] * 6 and codes[6] == 429
    guard.reset()
    assert client.post("/run", json={**body, "max_steps": 99}).status_code == 422
