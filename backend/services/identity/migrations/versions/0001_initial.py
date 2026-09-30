"""T0 初始领域表结构，无业务种子数据。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "identity_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("school_id", sa.String(64), nullable=False),
        sa.Column("credential_ref", mysql.BINARY(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("session_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.UniqueConstraint("credential_ref", name="uq_users_0"),
        sa.CheckConstraint("status IN ('active', 'disabled', 'deleted')", name="ck_users_0"),
        sa.CheckConstraint("session_version >= 1", name="ck_users_1"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_table(
        "app_sessions",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("user_id", mysql.BINARY(16), nullable=False),
        sa.Column("token_hash", mysql.BINARY(32), nullable=False),
        sa.Column("csrf_hash", mysql.BINARY(32), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("absolute_expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("last_seen_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("session_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.UniqueConstraint("token_hash", name="uq_app_sessions_0"),
        sa.CheckConstraint("session_version >= 1", name="ck_app_sessions_0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_app_sessions_0", "app_sessions", ["user_id", "revoked_at"])
    op.create_index("ix_app_sessions_1", "app_sessions", ["expires_at"])
    op.create_table(
        "consents",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("user_id", mysql.BINARY(16), nullable=False),
        sa.Column("agreement_version", sa.String(64), nullable=False),
        sa.Column("content_hash", mysql.BINARY(32), nullable=False),
        sa.Column("accepted_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("credential_use_allowed", sa.Boolean(), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_consents_0", "consents", ["user_id", "agreement_version", "accepted_at"])
    op.create_table(
        "login_attempts",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("browser_nonce_hash", mysql.BINARY(32), nullable=False),
        sa.Column("credential_ref", mysql.BINARY(16), nullable=True),
        sa.Column("user_id", mysql.BINARY(16), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.CheckConstraint(
            "state IN ('created', 'authenticating', 'staged', 'identity_committed', 'activating', 'activated', 'session_issued', 'failed', 'expired')",
            name="ck_login_attempts_0",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_login_attempts_0", "login_attempts", ["state", "expires_at"])
    op.create_table(
        "credential_operations",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("credential_ref", mysql.BINARY(16), nullable=False),
        sa.Column("expected_credential_version", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("saga_step", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("next_reconcile_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.UniqueConstraint(
            "owner_user_id", "expected_credential_version", name="uq_credential_operations_0"
        ),
        sa.CheckConstraint(
            "state IN ('accepted', 'running', 'reconciling', 'unknown', 'succeeded', 'failed', 'cancelled')",
            name="ck_credential_operations_0",
        ),
        sa.CheckConstraint("expected_credential_version >= 1", name="ck_credential_operations_1"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "ix_credential_operations_0", "credential_operations", ["state", "next_reconcile_at"]
    )
    op.create_table(
        "outbox_events",
        sa.Column("event_id", mysql.BINARY(16), nullable=False),
        sa.Column("type", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("aggregate_id", mysql.BINARY(16), nullable=False),
        sa.Column("aggregate_version", sa.BigInteger(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("available_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("publish_lease_owner", sa.String(128), nullable=True),
        sa.Column("publish_lease_until", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("published_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.CheckConstraint(
            "schema_version >= 1 AND aggregate_version >= 1", name="ck_outbox_events_0"
        ),
        sa.CheckConstraint("publish_attempts >= 0", name="ck_outbox_events_1"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_outbox_events_0", "outbox_events", ["published_at", "available_at"])
    op.create_index("ix_outbox_events_1", "outbox_events", ["publish_lease_until"])
    op.create_table(
        "inbox_events",
        sa.Column("consumer_name", sa.String(128), nullable=False),
        sa.Column("event_id", mysql.BINARY(16), nullable=False),
        sa.Column("processed_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.PrimaryKeyConstraint("consumer_name", "event_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )


def downgrade():
    op.drop_table("inbox_events")
    op.drop_table("outbox_events")
    op.drop_table("credential_operations")
    op.drop_table("login_attempts")
    op.drop_table("consents")
    op.drop_table("app_sessions")
    op.drop_table("users")
