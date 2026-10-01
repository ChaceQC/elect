"""二维码合并请求仍保存每个幂等键的原操作引用。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "payment_0003"
down_revision = "payment_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payment_qr_requests",
        sa.Column("owner_user_id", mysql.BINARY(16), primary_key=True),
        sa.Column("key_hash", mysql.BINARY(32), primary_key=True),
        sa.Column("request_digest", mysql.BINARY(32), nullable=False),
        sa.Column("operation_id", mysql.BINARY(16), nullable=False),
        sa.ForeignKeyConstraint(["operation_id"], ["payment_operations.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )


def downgrade():
    op.drop_table("payment_qr_requests")
