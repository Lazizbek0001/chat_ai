"""Drop the agent_tasks table: agents and tasks were removed.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
import sqlalchemy as sa
from alembic import op

from src.db import GUID

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    if "agent_tasks" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("agent_tasks")


def downgrade():
    if "agent_tasks" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "agent_tasks",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("user_id", GUID(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("agent", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("pending_calls", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index("ix_agent_tasks_user_id", "agent_tasks", ["user_id"])
    op.create_index("ix_agent_tasks_status", "agent_tasks", ["status"])
