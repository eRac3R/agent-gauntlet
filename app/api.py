"""FastAPI service: run the agent, stream its steps live, run eval suites, compare runs."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from app.agent import iter_agent, run_agent
from app.brains import list_agents, make_brain
from app.models import EvalRequest, FaultKind, FaultSpec, RunRequest, Trajectory
from gauntlet import store
from gauntlet.metrics import load_cases
from gauntlet.runner import case_dict, run_suite

app = FastAPI(title="Agent Gauntlet", version="1.0.0", description="Chaos-test and grade AI agents.")
STATIC = Path(__file__).parent / "static"


def _brain(name: str):
    try:
        return make_brain(name)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:  # e.g. the local LLM endpoint is not running
        raise HTTPException(503, f"could not start agent {name!r}: {exc}")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC / "dashboard.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/agents")
def agents():
    return list_agents()


@app.get("/cases")
def cases():
    return [case_dict(c) for c in load_cases()]


@app.get("/faults")
def faults():
    return [k.value for k in FaultKind]


@app.post("/run", response_model=Trajectory)
def run(req: RunRequest):
    return run_agent(req.query, _brain(req.agent), req.fault, req.max_steps)


@app.get("/run/stream")
async def run_stream(
    query: str,
    agent: str = "resilient",
    fault_tool: str | None = None,
    fault_kind: FaultKind = FaultKind.none,
    delay: float = Query(0.6, ge=0, le=3),
):
    brain = _brain(agent)
    fault = FaultSpec(tool=fault_tool, kind=fault_kind)

    async def events():
        for kind, payload in iter_agent(query, brain, fault):
            yield f"event: {kind}\ndata: {payload.model_dump_json()}\n\n"
            if kind == "step":
                await asyncio.sleep(delay)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/eval")
def evaluate(req: EvalRequest):
    _brain(req.agent)
    out = run_suite(req.agent, req.case_ids)
    return {k: v for k, v in out.items() if k != "results"} | {
        "results": [
            {"case_id": r["case"]["id"], "category": r["case"]["category"], "passed": r["score"]["passed"],
             "score": r["score"]["overall"], "notes": r["score"]["notes"], "path": r["traj"]["steps"] and [s["tool"] for s in r["traj"]["steps"]]}
            for r in out["results"]
        ]
    }


@app.get("/runs")
def runs():
    return store.list_runs()


@app.get("/runs/{run_id}")
def run_detail(run_id: int):
    found = store.get_run(run_id)
    if not found:
        raise HTTPException(404, "run not found")
    return found


@app.get("/compare")
def compare(baseline: int, candidate: int):
    try:
        return store.compare_runs(baseline, candidate)
    except KeyError:
        raise HTTPException(404, "run not found")


@app.get("/heatmap")
def heatmap():
    return store.heatmap()
