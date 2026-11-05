"""SQLite run history."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "gauntlet.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT NOT NULL, created_at REAL NOT NULL,
  n INTEGER, pass_rate REAL, avg_score REAL, tokens INTEGER, cost_usd REAL
);
CREATE TABLE IF NOT EXISTS results (
  run_id INTEGER NOT NULL, case_id TEXT NOT NULL, category TEXT, fault_kind TEXT,
  passed INTEGER, score REAL, scores_json TEXT, trajectory_json TEXT,
  PRIMARY KEY (run_id, case_id)
);
"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    db = sqlite3.connect(str(path or os.getenv("GAUNTLET_DB", DEFAULT_DB)))
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def save_run(agent: str, results: list[dict], path=None) -> int:
    """results: dicts with case, score (dict) and traj (dict)."""
    n = len(results)
    passed = sum(r["score"]["passed"] for r in results)
    tokens = sum(r["traj"]["tokens_in"] + r["traj"]["tokens_out"] for r in results)
    cost = sum(r["traj"]["cost_usd"] for r in results)
    avg = sum(r["score"]["overall"] for r in results) / max(n, 1)
    with connect(path) as db:
        cur = db.execute(
            "INSERT INTO runs (agent, created_at, n, pass_rate, avg_score, tokens, cost_usd) VALUES (?,?,?,?,?,?,?)",
            (agent, time.time(), n, passed / max(n, 1), avg, tokens, cost),
        )
        run_id = cur.lastrowid
        db.executemany(
            "INSERT INTO results VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    run_id, r["case"]["id"], r["case"]["category"], r["case"]["fault"]["kind"],
                    int(r["score"]["passed"]), r["score"]["overall"],
                    json.dumps(r["score"]), json.dumps(r["traj"]),
                )
                for r in results
            ],
        )
    return run_id


def list_runs(limit: int = 50, path=None) -> list[dict]:
    with connect(path) as db:
        return [dict(r) for r in db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))]


def get_run(run_id: int, path=None) -> dict | None:
    with connect(path) as db:
        run = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not run:
            return None
        rows = db.execute("SELECT * FROM results WHERE run_id=? ORDER BY case_id", (run_id,)).fetchall()
    results = [
        {**dict(r), "scores": json.loads(r["scores_json"]), "trajectory": json.loads(r["trajectory_json"])}
        for r in rows
    ]
    for r in results:
        r.pop("scores_json"), r.pop("trajectory_json")
    return {**dict(run), "results": results}


def latest_by_agent(path=None) -> dict[str, int]:
    with connect(path) as db:
        rows = db.execute("SELECT agent, MAX(id) AS id FROM runs GROUP BY agent").fetchall()
    return {r["agent"]: r["id"] for r in rows}


def compare_runs(a_id: int, b_id: int, path=None) -> dict:
    a, b = get_run(a_id, path), get_run(b_id, path)
    if not a or not b:
        raise KeyError("run not found")
    ap = {r["case_id"]: r for r in a["results"]}
    bp = {r["case_id"]: r for r in b["results"]}
    regressions, fixes = [], []
    for cid in ap.keys() & bp.keys():
        if ap[cid]["passed"] and not bp[cid]["passed"]:
            regressions.append({"case_id": cid, "category": ap[cid]["category"], "from": ap[cid]["score"], "to": bp[cid]["score"]})
        elif not ap[cid]["passed"] and bp[cid]["passed"]:
            fixes.append({"case_id": cid, "category": ap[cid]["category"], "from": ap[cid]["score"], "to": bp[cid]["score"]})
    return {
        "baseline": {k: a[k] for k in ("id", "agent", "pass_rate", "avg_score")},
        "candidate": {k: b[k] for k in ("id", "agent", "pass_rate", "avg_score")},
        "regressions": sorted(regressions, key=lambda x: x["case_id"]),
        "fixes": sorted(fixes, key=lambda x: x["case_id"]),
    }


def heatmap(path=None) -> dict:
    """pass-rate grid: fault category x agent, from each agent's latest run."""
    latest = latest_by_agent(path)
    grid: dict[str, dict[str, float]] = {}
    with connect(path) as db:
        for agent, run_id in latest.items():
            rows = db.execute(
                "SELECT category, AVG(passed) AS rate FROM results WHERE run_id=? GROUP BY category", (run_id,)
            ).fetchall()
            for r in rows:
                grid.setdefault(r["category"], {})[agent] = round(r["rate"], 3)
    return {"agents": sorted(latest), "categories": sorted(grid), "grid": grid}
