"""Run the dataset against an agent, score it, optionally persist."""
from __future__ import annotations

import dataclasses
from typing import Callable

from app.agent import run_agent
from app.brains import make_brain
from gauntlet import store
from gauntlet.metrics import Case, load_cases, score_case


def case_dict(case: Case) -> dict:
    d = dataclasses.asdict(case)
    d["fault"] = case.fault.model_dump(mode="json")
    return d


def run_case(agent: str, case: Case, brain=None) -> dict:
    traj = run_agent(case.query, brain or make_brain(agent), case.fault)
    return {"case": case_dict(case), "score": score_case(case, traj).to_dict(), "traj": traj.model_dump(mode="json")}


def run_suite(
    agent: str,
    case_ids: list[str] | None = None,
    persist: bool = True,
    on_result: Callable[[dict], None] | None = None,
) -> dict:
    cases = [c for c in load_cases() if not case_ids or c.id in case_ids]
    brain = make_brain(agent)
    results = []
    for case in cases:
        r = run_case(agent, case, brain)
        results.append(r)
        if on_result:
            on_result(r)
    run_id = store.save_run(agent, results) if persist else None
    n = len(results)
    return {
        "run_id": run_id,
        "agent": agent,
        "n": n,
        "pass_rate": sum(r["score"]["passed"] for r in results) / max(n, 1),
        "avg_score": sum(r["score"]["overall"] for r in results) / max(n, 1),
        "tokens": sum(r["traj"]["tokens_in"] + r["traj"]["tokens_out"] for r in results),
        "cost_usd": sum(r["traj"]["cost_usd"] for r in results),
        "results": results,
    }
