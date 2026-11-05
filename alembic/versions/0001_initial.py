"""initial schema: runs and results

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent", sa.String(64), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("n", sa.Integer, nullable=False),
        sa.Column("pass_rate", sa.Float, nullable=False),
        sa.Column("avg_score", sa.Float, nullable=False),
        sa.Column("tokens", sa.Integer, nullable=False),
        sa.Column("cost_usd", sa.Float, nullable=False),
    )
    op.create_index("ix_runs_agent", "runs", ["agent"])
    op.create_table(
        "results",
        sa.Column("run_id", sa.Integer, sa.ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("case_id", sa.String(64), primary_key=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("fault_kind", sa.String(32), nullable=False),
        sa.Column("passed", sa.Boolean, nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("scores", sa.JSON, nullable=False),
        sa.Column("trajectory", sa.JSON, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("results")
    op.drop_index("ix_runs_agent", table_name="runs")
    op.drop_table("runs")
