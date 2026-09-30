"""T0 初始领域表结构，无业务种子数据。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "room_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rooms",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("school_id", sa.String(64), nullable=False),
        sa.Column("school_room_id", sa.String(128), nullable=False),
        sa.Column("building_name", sa.String(128), nullable=False),
        sa.Column("room_no", sa.String(64), nullable=False),
        sa.Column("meter_code", sa.String(128), nullable=True),
        sa.Column("metadata_version", sa.BigInteger(), nullable=False),
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
        sa.UniqueConstraint("school_id", "school_room_id", name="uq_rooms_0"),
        sa.CheckConstraint("metadata_version >= 1", name="ck_rooms_0"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_table(
        "room_bindings",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("room_id", mysql.BINARY(16), nullable=False),
        sa.Column("school_relation_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_confirmed_at", mysql.DATETIME(fsp=6), nullable=True),
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
        sa.UniqueConstraint("owner_user_id", "room_id", name="uq_room_bindings_0"),
        sa.UniqueConstraint("id", "owner_user_id", name="uq_room_bindings_1"),
        sa.CheckConstraint(
            "status IN ('active', 'rechecking', 'inactive')", name="ck_room_bindings_0"
        ),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_room_bindings_0", "room_bindings", ["owner_user_id", "status"])
    op.create_table(
        "room_operations",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("target_room_id", mysql.BINARY(16), nullable=True),
        sa.Column("target_binding_id", mysql.BINARY(16), nullable=True),
        sa.Column("idempotency_key_hash", mysql.BINARY(32), nullable=True),
        sa.Column("request_digest", mysql.BINARY(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("saga_step", sa.String(32), nullable=False),
        sa.Column("upstream_operation_id", mysql.BINARY(16), nullable=True),
        sa.Column("next_reconcile_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("expected_preference_version", sa.BigInteger(), nullable=True),
        sa.Column("committed_preference_version", sa.BigInteger(), nullable=True),
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
            "open_binding_target",
            mysql.BINARY(16),
            sa.Computed(
                "IF(type = 'bind_room' AND state IN ('accepted', 'running', 'reconciling', 'unknown'), target_room_id, NULL)",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "open_switch_owner",
            mysql.BINARY(16),
            sa.Computed(
                "IF(type = 'switch_default' AND state IN ('accepted', 'running', 'reconciling', 'unknown'), owner_user_id, NULL)",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "owner_user_id", "type", "idempotency_key_hash", name="uq_room_operations_0"
        ),
        sa.UniqueConstraint("owner_user_id", "open_binding_target", name="uq_room_operations_1"),
        sa.UniqueConstraint("open_switch_owner", name="uq_room_operations_2"),
        sa.CheckConstraint(
            "type IN ('binding_sync', 'bind_room', 'switch_default', 'balance_refresh', 'history_sync')",
            name="ck_room_operations_0",
        ),
        sa.CheckConstraint(
            "state IN ('accepted', 'running', 'reconciling', 'unknown', 'succeeded', 'failed', 'cancelled')",
            name="ck_room_operations_1",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("ix_room_operations_0", "room_operations", ["state", "next_reconcile_at"])
    op.create_index("ix_room_operations_1", "room_operations", ["owner_user_id", "state"])
    op.create_table(
        "room_preferences",
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("default_binding_id", mysql.BINARY(16), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("switch_operation_id", mysql.BINARY(16), nullable=True),
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
        sa.PrimaryKeyConstraint("owner_user_id"),
        sa.CheckConstraint("version >= 1", name="ck_room_preferences_0"),
        sa.CheckConstraint(
            "state IN ('ready', 'switching', 'blocked')", name="ck_room_preferences_1"
        ),
        sa.ForeignKeyConstraint(
            ["default_binding_id", "owner_user_id"],
            ["room_bindings.id", "room_bindings.owner_user_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["switch_operation_id"], ["room_operations.id"], ondelete="RESTRICT"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_table(
        "room_balance_cache",
        sa.Column("binding_id", mysql.BINARY(16), nullable=False),
        sa.Column("balance", sa.Numeric(14, 2), nullable=True),
        sa.Column("fetched_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("school_observed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("quality", sa.String(32), nullable=False),
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
        sa.PrimaryKeyConstraint("binding_id"),
        sa.ForeignKeyConstraint(["binding_id"], ["room_bindings.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_table(
        "history_syncs",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("binding_id", mysql.BINARY(16), nullable=False),
        sa.Column("operation_id", mysql.BINARY(16), nullable=False),
        sa.Column("requested_start", sa.Date(), nullable=False),
        sa.Column("requested_end", sa.Date(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("coverage", sa.String(32), nullable=False),
        sa.Column("fetched_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
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
        sa.UniqueConstraint("operation_id", name="uq_history_syncs_0"),
        sa.CheckConstraint(
            "status IN ('accepted', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_history_syncs_0",
        ),
        sa.CheckConstraint(
            "coverage IN ('complete', 'partial', 'unknown')", name="ck_history_syncs_1"
        ),
        sa.CheckConstraint("version >= 1", name="ck_history_syncs_2"),
        sa.CheckConstraint("requested_end >= requested_start", name="ck_history_syncs_3"),
        sa.ForeignKeyConstraint(["binding_id"], ["room_bindings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["operation_id"], ["room_operations.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "ix_history_syncs_0",
        "history_syncs",
        ["binding_id", "requested_start", "requested_end", "source"],
    )
    op.create_table(
        "history_sync_windows",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("sync_id", mysql.BINARY(16), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("cursor", sa.String(512), nullable=True),
        sa.Column("cancel_requested_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_until", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("execution_epoch", sa.BigInteger(), nullable=False),
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
        sa.UniqueConstraint("sync_id", "start_date", "end_date", name="uq_history_sync_windows_0"),
        sa.CheckConstraint(
            "state IN ('pending', 'running', 'retry_wait', 'succeeded', 'failed', 'cancelled')",
            name="ck_history_sync_windows_0",
        ),
        sa.CheckConstraint("execution_epoch >= 1", name="ck_history_sync_windows_1"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_history_sync_windows_2"),
        sa.CheckConstraint("end_date >= start_date", name="ck_history_sync_windows_3"),
        sa.ForeignKeyConstraint(["sync_id"], ["history_syncs.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "ix_history_sync_windows_0", "history_sync_windows", ["state", "next_attempt_at"]
    )
    op.create_index("ix_history_sync_windows_1", "history_sync_windows", ["state", "lease_until"])
    op.create_table(
        "school_history_records",
        sa.Column("id", mysql.BINARY(16), nullable=False, primary_key=True),
        sa.Column("binding_id", mysql.BINARY(16), nullable=False),
        sa.Column("request_room_id", sa.String(128), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_record_key", sa.String(128), nullable=True),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("source_time", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("source_timezone", sa.String(64), nullable=False),
        sa.Column("last_reading", sa.Numeric(18, 4), nullable=True),
        sa.Column("reading", sa.Numeric(18, 4), nullable=True),
        sa.Column("energy_usage", sa.Numeric(18, 4), nullable=True),
        sa.Column("charged_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("charge_status", sa.String(128), nullable=True),
        sa.Column("row_hash", mysql.BINARY(32), nullable=False),
        sa.Column("sync_id", mysql.BINARY(16), nullable=False),
        sa.Column("occurrence_index", sa.Integer(), nullable=False),
        sa.Column("snapshot_version", sa.BigInteger(), nullable=False),
        sa.Column("quality", sa.String(32), nullable=False),
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
            "binding_id", "source", "source_record_key", name="uq_school_history_records_0"
        ),
        sa.UniqueConstraint(
            "sync_id", "row_hash", "occurrence_index", name="uq_school_history_records_1"
        ),
        sa.CheckConstraint("occurrence_index >= 1", name="ck_school_history_records_0"),
        sa.CheckConstraint("snapshot_version >= 1", name="ck_school_history_records_1"),
        sa.ForeignKeyConstraint(["binding_id"], ["room_bindings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sync_id"], ["history_syncs.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "ix_school_history_records_0",
        "school_history_records",
        ["binding_id", "record_date", "source"],
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
    op.drop_table("school_history_records")
    op.drop_table("history_sync_windows")
    op.drop_table("history_syncs")
    op.drop_table("room_balance_cache")
    op.drop_table("room_preferences")
    op.drop_table("room_operations")
    op.drop_table("room_bindings")
    op.drop_table("rooms")
