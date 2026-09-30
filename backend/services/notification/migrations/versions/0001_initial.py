"""T0 初始领域表结构，无业务种子数据。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "notification_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_jobs",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("alert_slot_id", mysql.BINARY(16), nullable=False),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("email_ciphertext", mysql.LONGBLOB(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("email_version", sa.BigInteger(), nullable=False),
        sa.Column("template_version", sa.String(64), nullable=False),
        sa.Column("message_id", sa.String(256), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_until", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("execution_epoch", sa.BigInteger(), nullable=False),
        sa.Column("permit_id", mysql.BINARY(16), nullable=True),
        sa.Column("permit_expires_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
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
        sa.UniqueConstraint("alert_slot_id", name="uq_notification_jobs_0"),
        sa.UniqueConstraint("message_id", name="uq_notification_jobs_1"),
        sa.CheckConstraint(
            "state IN ('pending', 'sending', 'retry_wait', 'sent', 'failed', 'delivery_unknown', 'cancelled')",
            name="ck_notification_jobs_0",
        ),
        sa.CheckConstraint(
            "generation >= 1 AND email_version >= 1 AND version >= 1 AND execution_epoch >= 1",
            name="ck_notification_jobs_1",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_notification_jobs_2"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_notification_jobs_0", "notification_jobs", ["state", "next_attempt_at"])
    op.create_index("ix_notification_jobs_1", "notification_jobs", ["state", "lease_until"])
    op.create_table(
        "notification_attempts",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("job_id", mysql.BINARY(16), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("provider_result", sa.String(64), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
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
        sa.UniqueConstraint("job_id", "attempt_no", name="uq_notification_attempts_0"),
        sa.CheckConstraint("attempt_no >= 1", name="ck_notification_attempts_0"),
        sa.CheckConstraint(
            "state IN ('started', 'accepted', 'retryable', 'rejected', 'unknown', 'cancelled')",
            name="ck_notification_attempts_1",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["notification_jobs.id"], ondelete="RESTRICT"),
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
    op.drop_table("notification_attempts")
    op.drop_table("notification_jobs")
