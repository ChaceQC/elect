"""R4冻结迁移声明：归档与去重同库同事务，随既有加密全库备份恢复。"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql


def upgrade(op):
    op.create_table(
        "archive_records",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(200), nullable=False),
        sa.Column("format_version", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", mysql.BINARY(32), nullable=False),
        sa.Column("payload", mysql.LONGBLOB(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.UniqueConstraint("kind", "object_key", name="uq_archive_object"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    op.create_table(
        "cold_request_keys",
        sa.Column("owner_user_id", mysql.BINARY(16), primary_key=True),
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("key_hash", mysql.BINARY(32), primary_key=True),
        sa.Column("request_digest", mysql.BINARY(32), nullable=False),
        sa.Column("result_id", mysql.BINARY(16), nullable=False),
        sa.Column("archive_id", mysql.BINARY(16), nullable=False),
        sa.ForeignKeyConstraint(["archive_id"], ["archive_records.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    op.create_index("ix_cold_request_result", "cold_request_keys", ["kind", "result_id"])
    op.create_table(
        "cold_inbox_events",
        sa.Column("consumer_name", sa.String(128), primary_key=True),
        sa.Column("event_id", mysql.BINARY(16), primary_key=True),
        sa.Column("processed_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("archive_id", mysql.BINARY(16), nullable=False),
        sa.ForeignKeyConstraint(["archive_id"], ["archive_records.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    op.create_index("ix_inbox_retention", "inbox_events", ["processed_at", "event_id"])


def downgrade(op):
    raise RuntimeError("冷标识不可直接删除；须先停消费并回填热标识或保留兼容版本")
