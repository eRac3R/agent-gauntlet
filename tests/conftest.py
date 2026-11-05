import os

os.environ["GAUNTLET_SKIP_DOTENV"] = "1"  # before any app import: never touch the real database in tests
os.environ["DEEPEVAL_DISABLE_DOTENV"] = "1"  # deepeval would otherwise autoload .env.local on import
for _k in ("DATABASE_URL", "GAUNTLET_LLM_BASE_URL", "GAUNTLET_LLM_MODEL", "GAUNTLET_LLM_API_KEY"):
    os.environ.pop(_k, None)

import pytest

from app import guard

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    guard.reset()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("GAUNTLET_DB", str(tmp_path / "test.db"))
