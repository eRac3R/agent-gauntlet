from gauntlet import store
from gauntlet.db import database_url, get_engine
from gauntlet.runner import run_suite


def test_defaults_to_sqlite_and_normalises_postgres_urls(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert database_url().startswith("sqlite")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db?sslmode=require")
    assert database_url().startswith("postgresql+psycopg://u:p@host/db")
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host/db")
    assert database_url().startswith("postgresql+psycopg://")


def test_run_round_trip_and_regression_compare():
    good = run_suite("resilient")
    bad = run_suite("naive")
    assert store.get_run(good["run_id"])["n"] == 20
    assert len(store.list_runs()) == 2
    cmp = store.compare_runs(good["run_id"], bad["run_id"])
    assert cmp["regressions"] and not cmp["fixes"]
    assert store.heatmap()["grid"]["happy"]["resilient"] == 1.0


def test_old_runs_are_pruned(monkeypatch):
    monkeypatch.setattr(store, "MAX_RUNS", 3)
    for _ in range(5):
        run_suite("resilient", case_ids=["happy-01"])
    assert len(store.list_runs(limit=50)) == 3
