"""T5 可释放序号、投递镜像与独立采集故障事件。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "monitoring_0005"
down_revision = "monitoring_0004"
branch_labels = None
depends_on = None


def upgrade():
    # 先建 episode 外键所需索引，再替换原唯一索引。
    op.create_index("ix_alert_slots_episode", "alert_slots", ["episode_id"])
    op.drop_constraint("uq_alert_slots_0", "alert_slots", type_="unique")
    op.add_column(
        "alert_slots",
        sa.Column(
            "occupied_ordinal",
            sa.Integer(),
            sa.Computed("IF(state IN ('cancelled','failed'), NULL, ordinal)", persisted=True),
        ),
    )
    op.create_unique_constraint(
        "uq_alert_slots_occupied", "alert_slots", ["episode_id", "occupied_ordinal"]
    )
    # 历史 T3 验收 slot 允许共享样本；新增业务通过事务内样本检查防重。
    op.add_column(
        "alert_slots",
        sa.Column("delivery_version", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column("alert_slots", sa.Column("last_error_code", sa.String(64)))
    op.add_column("alert_slots", sa.Column("next_retry_at", mysql.DATETIME(fsp=6)))
    op.add_column("alert_slots", sa.Column("wake_at", mysql.DATETIME(fsp=6)))
    op.add_column(
        "monitors", sa.Column("failed_cycles", sa.Integer(), nullable=False, server_default="0")
    )
    op.create_table(
        "monitor_fault_episodes",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("monitor_id", mysql.BINARY(16), nullable=False),
        sa.Column("opened_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("closed_at", mysql.DATETIME(fsp=6)),
        sa.Column("failed_cycles", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(64), nullable=False),
        sa.Column(
            "open_monitor_id",
            mysql.BINARY(16),
            sa.Computed("IF(closed_at IS NULL, monitor_id, NULL)", persisted=True),
        ),
        sa.UniqueConstraint("open_monitor_id", name="uq_monitor_fault_open"),
        sa.CheckConstraint("failed_cycles > 3", name="ck_monitor_fault_cycles"),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitors.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )


def downgrade():
    # 有取消后重用的历史序号时禁止退回旧唯一键，应先人工对账。
    op.drop_table("monitor_fault_episodes")
    op.drop_column("monitors", "failed_cycles")
    for name in ["wake_at", "next_retry_at", "last_error_code", "delivery_version"]:
        op.drop_column("alert_slots", name)
    op.drop_constraint("uq_alert_slots_occupied", "alert_slots", type_="unique")
    op.drop_column("alert_slots", "occupied_ordinal")
    op.create_unique_constraint("uq_alert_slots_0", "alert_slots", ["episode_id", "ordinal"])
    op.drop_index("ix_alert_slots_episode", table_name="alert_slots")
