"""T0 初始领域表结构，无业务种子数据。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "payment_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payment_orders",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("binding_id", mysql.BINARY(16), nullable=False),
        sa.Column("binding_display_name", sa.String(256), nullable=False),
        sa.Column("credential_ref", mysql.BINARY(16), nullable=False),
        sa.Column("credential_version", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("idempotency_key_hash", mysql.BINARY(32), nullable=False),
        sa.Column("request_digest", mysql.BINARY(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("upstream_operation_id", mysql.BINARY(16), nullable=False),
        sa.Column("sdgl_order_id_ciphertext", mysql.LONGBLOB(), nullable=True),
        sa.Column("prepay_id_ciphertext", mysql.LONGBLOB(), nullable=True),
        sa.Column("pay_url_ciphertext", mysql.LONGBLOB(), nullable=True),
        sa.Column("school_status_raw_code", sa.String(128), nullable=True),
        sa.Column("last_checked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
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
        sa.Column(
            "unresolved_binding_id",
            mysql.BINARY(16),
            sa.Computed(
                "IF(state IN ('created','submitting','awaiting_payment','submit_unknown','status_unknown'), binding_id, NULL)",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.UniqueConstraint("owner_user_id", "idempotency_key_hash", name="uq_payment_orders_0"),
        sa.UniqueConstraint("upstream_operation_id", name="uq_payment_orders_1"),
        sa.UniqueConstraint("owner_user_id", "unresolved_binding_id", name="uq_payment_orders_2"),
        sa.CheckConstraint("amount > 0", name="ck_payment_orders_0"),
        sa.CheckConstraint("currency = 'CNY'", name="ck_payment_orders_1"),
        sa.CheckConstraint("version >= 1 AND credential_version >= 1", name="ck_payment_orders_2"),
        sa.CheckConstraint(
            "state IN ('created', 'submitting', 'awaiting_payment', 'paid_confirmed', 'submit_unknown', 'status_unknown', 'rejected', 'expired_confirmed', 'closed_confirmed')",
            name="ck_payment_orders_3",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_payment_orders_0", "payment_orders", ["state", "last_checked_at"])
    op.create_table(
        "payment_operations",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("order_id", mysql.BINARY(16), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("idempotency_key_hash", mysql.BINARY(32), nullable=True),
        sa.Column("request_digest", mysql.BINARY(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_until", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("execution_epoch", sa.BigInteger(), nullable=False),
        sa.Column("next_attempt_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("qr_expires_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
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
            "owner_user_id", "kind", "idempotency_key_hash", name="uq_payment_operations_0"
        ),
        sa.CheckConstraint(
            "kind IN ('create_order', 'qr_refresh', 'status_check')", name="ck_payment_operations_0"
        ),
        sa.CheckConstraint(
            "state IN ('accepted', 'running', 'reconciling', 'unknown', 'succeeded', 'failed', 'cancelled')",
            name="ck_payment_operations_1",
        ),
        sa.CheckConstraint("execution_epoch >= 1", name="ck_payment_operations_2"),
        sa.ForeignKeyConstraint(["order_id"], ["payment_orders.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_payment_operations_0", "payment_operations", ["state", "next_attempt_at"])
    op.create_index("ix_payment_operations_1", "payment_operations", ["state", "lease_until"])
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
    op.drop_table("payment_operations")
    op.drop_table("payment_orders")
