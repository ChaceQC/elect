"""旧二维码映射以迁移时刻为保守创建时间，不推断原日期。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "payment_0005"
down_revision = "payment_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payment_qr_requests", sa.Column("created_at", mysql.DATETIME(fsp=6),
                  nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")))
    op.create_index("ix_payment_qr_budget", "payment_qr_requests", ["owner_user_id", "created_at"])


def downgrade():
    op.drop_index("ix_payment_qr_budget", table_name="payment_qr_requests")
    op.drop_column("payment_qr_requests", "created_at")
