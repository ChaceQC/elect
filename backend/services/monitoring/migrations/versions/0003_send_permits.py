"""T3 发送授权的持久许可与 job/epoch 去重，实际 SMTP 留待 T5。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "monitoring_0003"
down_revision = "monitoring_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "send_permits",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("alert_slot_id", mysql.BINARY(16), nullable=False),
        sa.Column("job_id", mysql.BINARY(16), nullable=False),
        sa.Column("execution_epoch", sa.BigInteger(), nullable=False),
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
        sa.UniqueConstraint("job_id", "execution_epoch", name="uq_send_permit_job_epoch"),
        sa.CheckConstraint("execution_epoch>=1", name="ck_send_permit_epoch"),
        sa.ForeignKeyConstraint(["alert_slot_id"], ["alert_slots.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )


def downgrade():
    op.drop_table("send_permits")
