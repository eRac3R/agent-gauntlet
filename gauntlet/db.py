"""Database layer: SQLAlchemy 2.0 models, engine factory, migrations.

DATABASE_URL selects the backend:
  - unset            -> local SQLite file (free, zero setup; used by tests/CI/local runs)
  - postgresql://... -> PostgreSQL (e.g. Neon free tier for the hosted demo)
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.pool import NullPool
from sqlalchemy.types import JSON

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE = ROOT / "gauntlet.db"
ALEMBIC_DIR = ROOT / "alembic"


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[float] = mapped_column(Float)
    n: Mapped[int] = mapped_column(Integer)
    pass_rate: Mapped[float] = mapped_column(Float)
    avg_score: Mapped[float] = mapped_column(Float)
    tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float)

    results: Mapped[list["Result"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class Result(Base):
    __tablename__ = "results"

    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(32))
    fault_kind: Mapped[str] = mapped_column(String(32))
    passed: Mapped[bool] = mapped_column(Boolean)
    score: Mapped[float] = mapped_column(Float)
    scores: Mapped[dict] = mapped_column(JSON)
    trajectory: Mapped[dict] = mapped_column(JSON)

    run: Mapped[Run] = relationship(back_populates="results")


def database_url() -> str:
    """Resolve the URL fresh each call so tests can point at a temp database."""
    url = os.getenv("DATABASE_URL")
    if not url and os.getenv("GAUNTLET_DB"):
        url = f"sqlite:///{os.environ['GAUNTLET_DB']}"
    url = url or f"sqlite:///{DEFAULT_SQLITE}"
    # Accept the plain postgres:// / postgresql:// strings that Neon and Vercel hand out.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


_engines: dict[str, Engine] = {}
_migrated: set[str] = set()
_lock = threading.Lock()
_migrate_lock = threading.Lock()


def get_engine() -> Engine:
    url = database_url()
    with _lock:
        if url not in _engines:
            if url.startswith("sqlite"):
                _engines[url] = create_engine(url, connect_args={"check_same_thread": False})
            else:
                # NullPool + pre-ping: right for serverless hosts and for Neon, which suspends idle databases.
                _engines[url] = create_engine(url, poolclass=NullPool, pool_pre_ping=True, connect_args={"connect_timeout": 15})
        return _engines[url]


def connect_with_retry(engine: Engine, attempts: int = 4, delay: float = 1.5) -> None:
    """A suspended Neon database can refuse the very first connection while it wakes up."""
    for i in range(attempts):
        try:
            with engine.connect():
                return
        except OperationalError:
            if i == attempts - 1:
                raise
            time.sleep(delay * (i + 1))


def ensure_schema() -> Engine:
    """Run Alembic migrations to head once per database URL, then return the engine."""
    from alembic import command
    from alembic.config import Config

    engine = get_engine()
    url = database_url()
    # Alembic keeps its context in module globals, so concurrent upgrades in one process collide.
    with _migrate_lock:
        if url in _migrated:
            return engine
        connect_with_retry(engine)
        cfg = Config()
        cfg.set_main_option("script_location", str(ALEMBIC_DIR))
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
        _migrated.add(url)
    return engine
