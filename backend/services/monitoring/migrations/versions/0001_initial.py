"""T0 初始领域表结构，无业务种子数据。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "monitoring_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "monitors",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("binding_id", mysql.BINARY(16), nullable=True),
        sa.Column("credential_ref", mysql.BINARY(16), nullable=True),
        sa.Column("credential_version", sa.BigInteger(), nullable=True),
        sa.Column("desired_enabled", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("health", sa.String(32), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("repeat_limit", sa.Integer(), nullable=False),
        sa.Column("threshold", sa.Numeric(14, 2), nullable=False),
        sa.Column("email_ciphertext", mysql.LONGBLOB(), nullable=True),
        sa.Column("email_version", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("schedule_anchor_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("next_run_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("active_run_id", mysql.BINARY(16), nullable=True),
        sa.Column("last_success_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("last_retarget_operation_id", mysql.BINARY(16), nullable=True),
        sa.Column("current_episode_id", mysql.BINARY(16), nullable=True),
        sa.Column("last_sample_id", mysql.BINARY(16), nullable=True),
        sa.Column("first_enabled_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("last_email_sent_at", mysql.DATETIME(fsp=6), nullable=True),
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
        sa.UniqueConstraint("owner_user_id", name="uq_monitors_0"),
        sa.CheckConstraint(
            "state IN ('active', 'disabled', 'requires_reauth', 'blocked_room', 'retargeting')",
            name="ck_monitors_0",
        ),
        sa.CheckConstraint(
            "health IN ('healthy', 'degraded', 'unavailable')", name="ck_monitors_1"
        ),
        sa.CheckConstraint("interval_minutes BETWEEN 60 AND 1440", name="ck_monitors_2"),
        sa.CheckConstraint("repeat_limit BETWEEN 1 AND 5", name="ck_monitors_3"),
        sa.CheckConstraint("threshold > 0 AND threshold <= 10000.00", name="ck_monitors_4"),
        sa.CheckConstraint(
            "email_version >= 1 AND version >= 1 AND generation >= 1", name="ck_monitors_5"
        ),
        sa.CheckConstraint("consecutive_failures >= 0", name="ck_monitors_6"),
        sa.CheckConstraint(
            "state <> 'active' OR (binding_id IS NOT NULL AND credential_ref IS NOT NULL AND desired_enabled = 1)",
            name="ck_monitors_7",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_monitors_0", "monitors", ["state", "next_run_at"])
    op.create_table(
        "monitor_runs",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("monitor_id", mysql.BINARY(16), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("scheduled_for", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("binding_id", mysql.BINARY(16), nullable=False),
        sa.Column("credential_version", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_until", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("execution_epoch", sa.BigInteger(), nullable=False),
        sa.Column("cancel_requested_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
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
        sa.UniqueConstraint("monitor_id", "generation", "scheduled_for", name="uq_monitor_runs_0"),
        sa.UniqueConstraint("id", "monitor_id", name="uq_monitor_runs_1"),
        sa.CheckConstraint(
            "state IN ('pending', 'running', 'retry_wait', 'cancel_requested', 'succeeded', 'failed', 'cancelled')",
            name="ck_monitor_runs_0",
        ),
        sa.CheckConstraint(
            "generation >= 1 AND version >= 1 AND credential_version >= 1 AND execution_epoch >= 1",
            name="ck_monitor_runs_1",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_monitor_runs_2"),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitors.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_monitor_runs_0", "monitor_runs", ["state", "next_attempt_at"])
    op.create_index("ix_monitor_runs_1", "monitor_runs", ["state", "lease_until"])
    op.create_table(
        "monitor_run_requests",
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("idempotency_key_hash", mysql.BINARY(32), nullable=False),
        sa.Column("request_digest", mysql.BINARY(32), nullable=False),
        sa.Column("run_id", mysql.BINARY(16), nullable=False),
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
        sa.PrimaryKeyConstraint("owner_user_id", "idempotency_key_hash"),
        sa.ForeignKeyConstraint(["run_id"], ["monitor_runs.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_monitor_run_requests_0", "monitor_run_requests", ["expires_at"])
    op.create_table(
        "monitor_attempts",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("run_id", mysql.BINARY(16), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(128), nullable=False),
        sa.Column("execution_epoch", sa.BigInteger(), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
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
        sa.UniqueConstraint("run_id", "attempt_no", name="uq_monitor_attempts_0"),
        sa.CheckConstraint(
            "attempt_no >= 1 AND execution_epoch >= 1", name="ck_monitor_attempts_0"
        ),
        sa.CheckConstraint(
            "outcome IN ('running', 'succeeded', 'retryable', 'failed', 'cancelled', 'fenced')",
            name="ck_monitor_attempts_1",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["monitor_runs.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_table(
        "monitor_samples",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("run_id", mysql.BINARY(16), nullable=False),
        sa.Column("monitor_id", mysql.BINARY(16), nullable=False),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("binding_id", mysql.BINARY(16), nullable=False),
        sa.Column("captured_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("balance", sa.Numeric(14, 2), nullable=False),
        sa.Column("previous_sample_id", mysql.BINARY(16), nullable=True),
        sa.Column("balance_delta", sa.Numeric(14, 2), nullable=True),
        sa.Column("meter_last_reading", sa.Numeric(18, 4), nullable=True),
        sa.Column("meter_reading", sa.Numeric(18, 4), nullable=True),
        sa.Column("meter_delta", sa.Numeric(18, 4), nullable=True),
        sa.Column("meter_record_date", sa.Date(), nullable=True),
        sa.Column("meter_source_record_key", sa.String(128), nullable=True),
        sa.Column("quality", sa.String(32), nullable=False),
        sa.Column("credential_version", sa.BigInteger(), nullable=False),
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
        sa.UniqueConstraint("run_id", name="uq_monitor_samples_0"),
        sa.CheckConstraint(
            "quality IN ('balance_only', 'meter_not_realtime', 'meter_inconsistent', 'meter_negative_delta')",
            name="ck_monitor_samples_0",
        ),
        sa.CheckConstraint("credential_version >= 1", name="ck_monitor_samples_1"),
        sa.ForeignKeyConstraint(
            ["run_id", "monitor_id"],
            ["monitor_runs.id", "monitor_runs.monitor_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_sample_id"], ["monitor_samples.id"], ondelete="RESTRICT"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "ix_monitor_samples_0",
        "monitor_samples",
        ["owner_user_id", "binding_id", "captured_at", "id"],
    )
    op.create_table(
        "alert_episodes",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("monitor_id", mysql.BINARY(16), nullable=False),
        sa.Column("binding_id", mysql.BINARY(16), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("opened_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("closed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("threshold", sa.Numeric(14, 2), nullable=False),
        sa.Column("recovery_threshold", sa.Numeric(14, 2), nullable=False),
        sa.Column("sent_count", sa.Integer(), nullable=False),
        sa.Column("reserved_count", sa.Integer(), nullable=False),
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
            "open_monitor_id",
            mysql.BINARY(16),
            sa.Computed("IF(state = 'open', monitor_id, NULL)", persisted=True),
            nullable=True,
        ),
        sa.UniqueConstraint("open_monitor_id", name="uq_alert_episodes_0"),
        sa.CheckConstraint("state IN ('open', 'closed')", name="ck_alert_episodes_0"),
        sa.CheckConstraint("generation >= 1", name="ck_alert_episodes_1"),
        sa.CheckConstraint("sent_count >= 0 AND reserved_count >= 0", name="ck_alert_episodes_2"),
        sa.CheckConstraint("recovery_threshold >= threshold", name="ck_alert_episodes_3"),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitors.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_table(
        "alert_slots",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("episode_id", mysql.BINARY(16), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("sample_id", mysql.BINARY(16), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("email_version", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("send_lease_until", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("permit_id", mysql.BINARY(16), nullable=True),
        sa.Column("delivery_id", mysql.BINARY(16), nullable=True),
        sa.Column("authorized_at", mysql.DATETIME(fsp=6), nullable=True),
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
        sa.UniqueConstraint("episode_id", "ordinal", name="uq_alert_slots_0"),
        sa.CheckConstraint("ordinal BETWEEN 1 AND 5", name="ck_alert_slots_0"),
        sa.CheckConstraint("generation >= 1 AND email_version >= 1", name="ck_alert_slots_1"),
        sa.CheckConstraint(
            "state IN ('reserved', 'authorized', 'sent', 'delivery_unknown', 'failed', 'cancelled')",
            name="ck_alert_slots_2",
        ),
        sa.ForeignKeyConstraint(["episode_id"], ["alert_episodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sample_id"], ["monitor_samples.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_alert_slots_0", "alert_slots", ["state", "send_lease_until"])
    op.create_table(
        "control_operations",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("target_binding_id", mysql.BINARY(16), nullable=True),
        sa.Column("credential_ref", mysql.BINARY(16), nullable=True),
        sa.Column("expected_preference_version", sa.BigInteger(), nullable=True),
        sa.Column("committed_preference_version", sa.BigInteger(), nullable=True),
        sa.Column("generation", sa.BigInteger(), nullable=False),
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
        sa.CheckConstraint(
            "type IN ('retarget', 'credential_revoke', 'credential_update')",
            name="ck_control_operations_0",
        ),
        sa.CheckConstraint(
            "state IN ('prepared', 'committed', 'compensated')", name="ck_control_operations_1"
        ),
        sa.CheckConstraint("generation >= 1", name="ck_control_operations_2"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_control_operations_0", "control_operations", ["owner_user_id", "state"])
    op.create_table(
        "sample_snapshots",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("binding_id", mysql.BINARY(16), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("token_hash", mysql.BINARY(32), nullable=False),
        sa.Column("total", sa.BigInteger(), nullable=False),
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
        sa.UniqueConstraint("token_hash", name="uq_sample_snapshots_0"),
        sa.CheckConstraint("total >= 0", name="ck_sample_snapshots_0"),
        sa.CheckConstraint("end_date >= start_date", name="ck_sample_snapshots_1"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_sample_snapshots_0", "sample_snapshots", ["expires_at"])
    op.create_index("ix_sample_snapshots_1", "sample_snapshots", ["owner_user_id", "binding_id"])
    op.create_table(
        "sample_snapshot_items",
        sa.Column("snapshot_id", mysql.BINARY(16), nullable=False),
        sa.Column("position", sa.BigInteger(), nullable=False),
        sa.Column("sample_id", mysql.BINARY(16), nullable=False),
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
        sa.PrimaryKeyConstraint("snapshot_id", "position"),
        sa.UniqueConstraint("snapshot_id", "sample_id", name="uq_sample_snapshot_items_0"),
        sa.CheckConstraint("position >= 1", name="ck_sample_snapshot_items_0"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["sample_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sample_id"], ["monitor_samples.id"], ondelete="RESTRICT"),
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
    op.create_foreign_key(
        "fk_monitors_active_run",
        "monitors",
        "monitor_runs",
        ["active_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_monitors_episode",
        "monitors",
        "alert_episodes",
        ["current_episode_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_monitors_last_sample",
        "monitors",
        "monitor_samples",
        ["last_sample_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint("fk_monitors_active_run", "monitors", type_="foreignkey")
    op.drop_constraint("fk_monitors_episode", "monitors", type_="foreignkey")
    op.drop_constraint("fk_monitors_last_sample", "monitors", type_="foreignkey")
    op.drop_table("inbox_events")
    op.drop_table("outbox_events")
    op.drop_table("sample_snapshot_items")
    op.drop_table("sample_snapshots")
    op.drop_table("control_operations")
    op.drop_table("alert_slots")
    op.drop_table("alert_episodes")
    op.drop_table("monitor_samples")
    op.drop_table("monitor_attempts")
    op.drop_table("monitor_run_requests")
    op.drop_table("monitor_runs")
    op.drop_table("monitors")
