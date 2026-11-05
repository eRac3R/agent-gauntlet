import os

import pytest

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("GAUNTLET_DB", str(tmp_path / "test.db"))
