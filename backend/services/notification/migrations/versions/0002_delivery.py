"""T5 邮件快照和正文发送边界；无明文地址/凭据。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "notification_0002"
down_revision = "notification_0001"
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column("binding_display_name", sa.String(256), nullable=False, server_default=""),
        sa.Column("balance", sa.Numeric(14, 2), nullable=True),
        sa.Column("threshold", sa.Numeric(14, 2), nullable=True),
        sa.Column("captured_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("body_started_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("reported_version", sa.BigInteger(), nullable=False, server_default="0"),
    ]:
        op.add_column("notification_jobs", column)


def downgrade():
    for name in [
        "reported_version",
        "body_started_at",
        "captured_at",
        "threshold",
        "balance",
        "binding_display_name",
    ]:
        op.drop_column("notification_jobs", name)
