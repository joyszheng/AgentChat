"""add MCP gateway foundation tables and connection metadata

Revision ID: 0003_mcp_gateway_foundation
Revises: 0002_task_run_lease_retry
Create Date: 2026-07-17
"""

from __future__ import annotations

import hashlib
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_mcp_gateway_foundation"
down_revision: Union[str, Sequence[str], None] = "0002_task_run_lease_retry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NAMESPACE_PATTERN = re.compile(r"[^a-zA-Z0-9_-]+")
_MAX_NAMESPACE_LENGTH = 48


def _namespace(name: str, *, existing: set[str]) -> str:
    normalized = _NAMESPACE_PATTERN.sub("_", name).strip("_").lower() or "mcp"
    if len(normalized) > _MAX_NAMESPACE_LENGTH:
        suffix = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
        normalized = f"{normalized[:_MAX_NAMESPACE_LENGTH - 9]}_{suffix}"
    candidate = normalized
    counter = 2
    while candidate in existing:
        suffix = f"_{counter}"
        candidate = f"{normalized[:_MAX_NAMESPACE_LENGTH - len(suffix)]}{suffix}"
        counter += 1
    existing.add(candidate)
    return candidate


def upgrade() -> None:
    op.create_table(
        "mcp_auth_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("auth_type", sa.String(length=30), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mcp_auth_profiles_id"), "mcp_auth_profiles", ["id"], unique=False)
    op.create_index(op.f("ix_mcp_auth_profiles_name"), "mcp_auth_profiles", ["name"], unique=True)
    op.create_index(
        op.f("ix_mcp_auth_profiles_auth_type"),
        "mcp_auth_profiles",
        ["auth_type"],
        unique=False,
    )

    op.add_column("mcp_servers", sa.Column("namespace", sa.String(length=48), nullable=True))
    op.add_column(
        "mcp_servers",
        sa.Column("transport_config", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column("mcp_servers", sa.Column("auth_profile_id", sa.Integer(), nullable=True))
    op.add_column(
        "mcp_servers",
        sa.Column("config_revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "mcp_servers",
        sa.Column("active_revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("mcp_servers", sa.Column("protocol_version", sa.String(length=30), nullable=True))
    op.add_column(
        "mcp_servers",
        sa.Column("server_info", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        "mcp_servers",
        sa.Column("capabilities", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        "mcp_servers",
        sa.Column("catalog_status", sa.String(length=30), server_default="unknown", nullable=False),
    )
    op.add_column(
        "mcp_servers",
        sa.Column("catalog_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.batch_alter_table("mcp_servers") as batch_op:
        batch_op.create_foreign_key(
            "fk_mcp_servers_auth_profile_id",
            "mcp_auth_profiles",
            ["auth_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(op.f("ix_mcp_servers_namespace"), "mcp_servers", ["namespace"], unique=True)
    op.create_index(
        op.f("ix_mcp_servers_auth_profile_id"),
        "mcp_servers",
        ["auth_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mcp_servers_catalog_status"),
        "mcp_servers",
        ["catalog_status"],
        unique=False,
    )

    server_table = sa.table(
        "mcp_servers",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("transport", sa.String()),
        sa.column("url", sa.String()),
        sa.column("call_timeout_seconds", sa.Integer()),
        sa.column("last_health_status", sa.String()),
        sa.column("namespace", sa.String()),
        sa.column("transport_config", sa.JSON()),
        sa.column("catalog_status", sa.String()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            server_table.c.id,
            server_table.c.name,
            server_table.c.transport,
            server_table.c.url,
            server_table.c.call_timeout_seconds,
            server_table.c.last_health_status,
        ).order_by(server_table.c.id)
    ).mappings()
    namespaces: set[str] = set()
    for row in rows:
        connection.execute(
            server_table.update()
            .where(server_table.c.id == row["id"])
            .values(
                namespace=_namespace(row["name"], existing=namespaces),
                transport_config={
                    "transport": row["transport"],
                    "url": row["url"],
                    "connect_timeout_seconds": 10,
                    "request_timeout_seconds": row["call_timeout_seconds"],
                    "tls_verify": True,
                    "network_policy": "private_allowlist",
                },
                catalog_status=row["last_health_status"] or "unknown",
            )
        )

    op.create_table(
        "mcp_tool_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("server_id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("required_role", sa.String(length=30), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("approval_mode", sa.String(length=30), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("max_result_chars", sa.Integer(), nullable=True),
        sa.Column("schema_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id", "source_name", name="uq_mcp_tool_policy_server_name"),
    )
    op.create_index(op.f("ix_mcp_tool_policies_id"), "mcp_tool_policies", ["id"], unique=False)
    op.create_index(
        op.f("ix_mcp_tool_policies_server_id"),
        "mcp_tool_policies",
        ["server_id"],
        unique=False,
    )

    op.create_table(
        "mcp_call_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("call_id", sa.String(length=36), nullable=False),
        sa.Column("server_id", sa.Integer(), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("qualified_name", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("invocation_source", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("arguments_summary", sa.Text(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["chat_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column, unique in (
        ("id", False),
        ("call_id", True),
        ("server_id", False),
        ("qualified_name", False),
        ("user_id", False),
        ("conversation_id", False),
        ("invocation_source", False),
        ("status", False),
        ("created_at", False),
    ):
        op.create_index(op.f(f"ix_mcp_call_logs_{column}"), "mcp_call_logs", [column], unique=unique)

    op.create_table(
        "mcp_config_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        sa.table(
            "mcp_config_state",
            sa.column("id", sa.Integer()),
            sa.column("revision", sa.Integer()),
        ),
        [{"id": 1, "revision": 1}],
    )


def downgrade() -> None:
    op.drop_table("mcp_config_state")
    op.drop_table("mcp_call_logs")
    op.drop_table("mcp_tool_policies")
    op.drop_index(op.f("ix_mcp_servers_catalog_status"), table_name="mcp_servers")
    op.drop_index(op.f("ix_mcp_servers_auth_profile_id"), table_name="mcp_servers")
    op.drop_index(op.f("ix_mcp_servers_namespace"), table_name="mcp_servers")
    with op.batch_alter_table("mcp_servers") as batch_op:
        batch_op.drop_constraint("fk_mcp_servers_auth_profile_id", type_="foreignkey")
    for column in (
        "catalog_updated_at",
        "catalog_status",
        "capabilities",
        "server_info",
        "protocol_version",
        "active_revision",
        "config_revision",
        "auth_profile_id",
        "transport_config",
        "namespace",
    ):
        op.drop_column("mcp_servers", column)
    op.drop_table("mcp_auth_profiles")
