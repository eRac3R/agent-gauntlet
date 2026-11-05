import os

os.environ["GAUNTLET_SKIP_DOTENV"] = "1"  # before any app import: never touch the real database in tests

import pytest

from app import guard

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    guard.reset()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("GAUNTLET_DB", str(tmp_path / "test.db"))
