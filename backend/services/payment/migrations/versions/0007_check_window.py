"""订单自动处理窗口；旧订单按原创建时间解释，不批量改写存量。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "payment_0007"
down_revision = "payment_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payment_orders", sa.Column("check_deadline_at", mysql.DATETIME(fsp=6)))


def downgrade():
    op.drop_column("payment_orders", "check_deadline_at")
