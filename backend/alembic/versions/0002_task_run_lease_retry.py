"""add task run lease and retry columns

Revision ID: 0002_task_run_lease_retry
Revises: 089d0dcd96ef
Create Date: 2026-07-13

Adds:
- tasks.run_started_at: lease start timestamp for the stuck-task reaper.
- tasks.retry_count: consecutive failed attempts for the current due run.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_task_run_lease_retry"
down_revision: Union[str, Sequence[str], None] = "089d0dcd96ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("run_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "retry_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "retry_count")
    op.drop_column("tasks", "run_started_at")
