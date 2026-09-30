"""T0 初始领域表结构，无业务种子数据。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "school_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "school_credentials",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("school_id", sa.String(64), nullable=False),
        sa.Column("school_user_id_ciphertext", mysql.LONGBLOB(), nullable=False),
        sa.Column("ciphertext", mysql.LONGBLOB(), nullable=False),
        sa.Column("nonce", mysql.BINARY(12), nullable=False),
        sa.Column("wrapped_dek", mysql.LONGBLOB(), nullable=False),
        sa.Column("kek_version", sa.String(64), nullable=False),
        sa.Column("algorithm", sa.String(32), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("verified_at", mysql.DATETIME(fsp=6), nullable=False),
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
        sa.UniqueConstraint("owner_user_id", "school_id", name="uq_school_credentials_0"),
        sa.CheckConstraint(
            "status IN ('active', 'revoking', 'revoked', 'requires_reauth')",
            name="ck_school_credentials_0",
        ),
        sa.CheckConstraint("version >= 1", name="ck_school_credentials_1"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_table(
        "credential_staging",
        sa.Column("attempt_id", mysql.BINARY(16), nullable=False),
        sa.Column("credential_ref", mysql.BINARY(16), nullable=False),
        sa.Column("encrypted_payload", mysql.LONGBLOB(), nullable=False),
        sa.Column("wrapped_dek", mysql.LONGBLOB(), nullable=False),
        sa.Column("nonce", mysql.BINARY(12), nullable=False),
        sa.Column("kek_version", sa.String(64), nullable=False),
        sa.Column("algorithm", sa.String(32), nullable=False),
        sa.Column("candidate_version", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
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
        sa.PrimaryKeyConstraint("attempt_id"),
        sa.CheckConstraint(
            "state IN ('staged', 'activating', 'activated', 'expired', 'failed')",
            name="ck_credential_staging_0",
        ),
        sa.CheckConstraint("candidate_version >= 1", name="ck_credential_staging_1"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_credential_staging_0", "credential_staging", ["state", "expires_at"])
    op.create_table(
        "account_lookup",
        sa.Column("school_id", sa.String(64), nullable=False),
        sa.Column("key_version", sa.String(64), nullable=False),
        sa.Column("lookup_hash", mysql.BINARY(32), nullable=False),
        sa.Column("credential_id", mysql.BINARY(16), nullable=False),
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
        sa.PrimaryKeyConstraint("school_id", "key_version", "lookup_hash"),
        sa.ForeignKeyConstraint(["credential_id"], ["school_credentials.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_table(
        "upstream_operations",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("operation_type", sa.String(32), nullable=False),
        sa.Column("target_ref", sa.String(128), nullable=False),
        sa.Column("request_digest", mysql.BINARY(32), nullable=False),
        sa.Column("credential_version", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("dispatched_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("result_ref", mysql.BINARY(16), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("reconcile_at", mysql.DATETIME(fsp=6), nullable=True),
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
            "operation_type IN ('bind_room', 'create_order', 'E01', 'E02', 'E03', 'E04')",
            name="ck_upstream_operations_0",
        ),
        sa.CheckConstraint(
            "state IN ('prepared', 'dispatched', 'confirmed', 'rejected', 'reconciling', 'unknown')",
            name="ck_upstream_operations_1",
        ),
        sa.CheckConstraint("credential_version >= 1", name="ck_upstream_operations_2"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_upstream_operations_0", "upstream_operations", ["state", "reconcile_at"])
    op.create_table(
        "payment_sessions",
        sa.Column("order_id", mysql.BINARY(16), nullable=False),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("cookiejar_ciphertext", mysql.LONGBLOB(), nullable=True),
        sa.Column("hidden_fields_ciphertext", mysql.LONGBLOB(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=True),
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
        sa.PrimaryKeyConstraint("order_id"),
        sa.CheckConstraint("version >= 1", name="ck_payment_sessions_0"),
        sa.CheckConstraint(
            "state IN ('created', 'active', 'unknown', 'closed')", name="ck_payment_sessions_1"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
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
    op.drop_table("payment_sessions")
    op.drop_table("upstream_operations")
    op.drop_table("account_lookup")
    op.drop_table("credential_staging")
    op.drop_table("school_credentials")
