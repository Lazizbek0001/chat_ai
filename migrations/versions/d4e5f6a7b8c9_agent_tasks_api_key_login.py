"""Remove Authentik login (drop user.oidc_sub) and add the agent_tasks table.

Revision ID: d4e5f6a7b8c9
Revises: c7d8e9f0a1b2
"""
import sqlalchemy as sa
from alembic import op

from src.db import GUID

revision = "d4e5f6a7b8c9"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "user" in tables:
        if "ix_user_oidc_sub" in {i["name"] for i in inspector.get_indexes("user")}:
            op.drop_index("ix_user_oidc_sub", table_name="user")
        if "oidc_sub" in {c["name"] for c in inspector.get_columns("user")}:
            with op.batch_alter_table("user") as batch:
                batch.drop_column("oidc_sub")

    if "agent_tasks" not in tables:
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


def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if "agent_tasks" in tables:
        op.drop_table("agent_tasks")

    if "user" in tables:
        with op.batch_alter_table("user") as batch:
            batch.add_column(sa.Column("oidc_sub", sa.String(255), nullable=True))
        op.create_index("ix_user_oidc_sub", "user", ["oidc_sub"], unique=True)
