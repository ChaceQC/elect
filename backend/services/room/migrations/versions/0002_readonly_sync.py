"""T2 同步状态与只读任务租约；偏好默认仍由 T3 提交。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "room_0002"
down_revision = "room_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "rooms",
        "school_room_id",
        existing_type=sa.String(128),
        type_=sa.String(128, collation="utf8mb4_bin"),
        existing_nullable=False,
    )
    op.add_column("room_operations", sa.Column("lease_owner", sa.String(128), nullable=True))
    op.add_column("room_operations", sa.Column("lease_until", mysql.DATETIME(fsp=6), nullable=True))
    op.create_table(
        "room_sync_state",
        sa.Column("owner_user_id", mysql.BINARY(16), primary_key=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("last_synced_at", mysql.DATETIME(fsp=6), nullable=True),
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
        sa.CheckConstraint(
            "state IN ('loading','ready','empty','stale','failed')", name="ck_room_sync_state"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )


def downgrade():
    op.alter_column(
        "rooms",
        "school_room_id",
        existing_type=sa.String(128),
        type_=sa.String(128),
        existing_nullable=False,
    )
    op.drop_table("room_sync_state")
    op.drop_column("room_operations", "lease_until")
    op.drop_column("room_operations", "lease_owner")
