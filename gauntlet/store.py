"""Run history on top of SQLAlchemy. Works on SQLite (default) and PostgreSQL (DATABASE_URL)."""
from __future__ import annotations

import time

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from gauntlet.db import Result, Run, ensure_schema

MAX_RUNS = 300  # keep the free-tier database tiny: prune the oldest beyond this


def _session() -> Session:
    return Session(ensure_schema(), expire_on_commit=False)


def _run_dict(r: Run) -> dict:
    return {
        "id": r.id, "agent": r.agent, "created_at": r.created_at, "n": r.n,
        "pass_rate": r.pass_rate, "avg_score": r.avg_score, "tokens": r.tokens, "cost_usd": r.cost_usd,
    }


def save_run(agent: str, results: list[dict]) -> int:
    """results: dicts with case, score (dict) and traj (dict)."""
    n = len(results)
    run = Run(
        agent=agent, created_at=time.time(), n=n,
        pass_rate=sum(r["score"]["passed"] for r in results) / max(n, 1),
        avg_score=sum(r["score"]["overall"] for r in results) / max(n, 1),
        tokens=sum(r["traj"]["tokens_in"] + r["traj"]["tokens_out"] for r in results),
        cost_usd=sum(r["traj"]["cost_usd"] for r in results),
        results=[
            Result(
                case_id=r["case"]["id"], category=r["case"]["category"], fault_kind=r["case"]["fault"]["kind"],
                passed=bool(r["score"]["passed"]), score=r["score"]["overall"], scores=r["score"], trajectory=r["traj"],
            )
            for r in results
        ],
    )
    with _session() as db:
        db.add(run)
        db.commit()
        run_id = run.id
        keep = db.scalars(select(Run.id).order_by(Run.id.desc()).limit(MAX_RUNS)).all()
        if len(keep) == MAX_RUNS:
            db.execute(delete(Result).where(Result.run_id < min(keep)))
            db.execute(delete(Run).where(Run.id < min(keep)))
            db.commit()
    return run_id


def list_runs(limit: int = 50) -> list[dict]:
    with _session() as db:
        return [_run_dict(r) for r in db.scalars(select(Run).order_by(Run.id.desc()).limit(limit))]


def get_run(run_id: int) -> dict | None:
    with _session() as db:
        run = db.get(Run, run_id)
        if not run:
            return None
        rows = db.scalars(select(Result).where(Result.run_id == run_id).order_by(Result.case_id)).all()
        return {
            **_run_dict(run),
            "results": [
                {"run_id": x.run_id, "case_id": x.case_id, "category": x.category, "fault_kind": x.fault_kind,
                 "passed": int(x.passed), "score": x.score, "scores": x.scores, "trajectory": x.trajectory}
                for x in rows
            ],
        }


def latest_by_agent() -> dict[str, int]:
    with _session() as db:
        rows = db.execute(select(Run.agent, func.max(Run.id)).group_by(Run.agent)).all()
    return {agent: run_id for agent, run_id in rows}


def compare_runs(a_id: int, b_id: int) -> dict:
    a, b = get_run(a_id), get_run(b_id)
    if not a or not b:
        raise KeyError("run not found")
    ap = {r["case_id"]: r for r in a["results"]}
    bp = {r["case_id"]: r for r in b["results"]}
    regressions, fixes = [], []
    for cid in ap.keys() & bp.keys():
        item = {"case_id": cid, "category": ap[cid]["category"], "from": ap[cid]["score"], "to": bp[cid]["score"]}
        if ap[cid]["passed"] and not bp[cid]["passed"]:
            regressions.append(item)
        elif not ap[cid]["passed"] and bp[cid]["passed"]:
            fixes.append(item)
    return {
        "baseline": {k: a[k] for k in ("id", "agent", "pass_rate", "avg_score")},
        "candidate": {k: b[k] for k in ("id", "agent", "pass_rate", "avg_score")},
        "regressions": sorted(regressions, key=lambda x: x["case_id"]),
        "fixes": sorted(fixes, key=lambda x: x["case_id"]),
    }


def heatmap() -> dict:
    """pass-rate grid: fault category x agent, from each agent's latest run."""
    latest = latest_by_agent()
    grid: dict[str, dict[str, float]] = {}
    with _session() as db:
        for agent, run_id in latest.items():
            rows = db.execute(
                select(Result.category, Result.passed).where(Result.run_id == run_id)
            ).all()
            by_cat: dict[str, list[bool]] = {}
            for cat, passed in rows:
                by_cat.setdefault(cat, []).append(bool(passed))
            for cat, vals in by_cat.items():
                grid.setdefault(cat, {})[agent] = round(sum(vals) / len(vals), 3)
    return {"agents": sorted(latest), "categories": sorted(grid), "grid": grid}
