"""Add user.username (required, unique) and make user.email optional.

Existing users get their email as username, so they can keep logging in with it.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""
import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "user" not in inspector.get_table_names():
        return
    if "username" in {c["name"] for c in inspector.get_columns("user")}:
        return

    with op.batch_alter_table("user") as batch:
        batch.add_column(sa.Column("username", sa.String(150), nullable=True))

    user = sa.table("user", sa.column("username", sa.String), sa.column("email", sa.String))
    op.execute(user.update().values(username=sa.func.lower(user.c.email)))

    with op.batch_alter_table("user") as batch:
        batch.alter_column("username", existing_type=sa.String(150), nullable=False)
        batch.alter_column("email", existing_type=sa.String(320), nullable=True)
        batch.create_index("ix_user_username", ["username"], unique=True)


def downgrade():
    user = sa.table("user", sa.column("username", sa.String), sa.column("email", sa.String))
    # Email becomes required again: fill missing ones with the username.
    op.execute(user.update().where(user.c.email.is_(None)).values(email=user.c.username))
    with op.batch_alter_table("user") as batch:
        batch.drop_index("ix_user_username")
        batch.drop_column("username")
        batch.alter_column("email", existing_type=sa.String(320), nullable=False)
