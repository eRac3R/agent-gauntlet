"""Tiny .env loader for local development. Real environment variables always win."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINE = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def load_env() -> None:
    if os.getenv("GAUNTLET_SKIP_DOTENV"):  # tests must never read real credentials
        return
    for name in (".env.local", ".env"):
        path = ROOT / name
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            m = LINE.match(raw)
            if not m or raw.lstrip().startswith("#"):
                continue
            value = m.group(2).strip("'\"")
            os.environ.setdefault(m.group(1), value)
