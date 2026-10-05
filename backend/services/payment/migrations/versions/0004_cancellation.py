"""本地支付取消独立于学校支付终态；保留发送台账。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "payment_0004"
down_revision = "payment_0003"
branch_labels = None
depends_on = None


def slot(cancelled=False):
    return sa.Column(
        "unresolved_binding_id",
        mysql.BINARY(16),
        sa.Computed(
            "IF("
            + ("cancelled_at IS NULL AND " if cancelled else "")
            + "state IN ('created','submitting','awaiting_payment','submit_unknown',"
            "'status_unknown'),binding_id,NULL)",
            persisted=True,
        ),
    )


def replace_slot(cancelled):
    op.drop_constraint("uq_payment_orders_2", "payment_orders", type_="unique")
    op.drop_column("payment_orders", "unresolved_binding_id")
    op.add_column("payment_orders", slot(cancelled))
    op.create_unique_constraint(
        "uq_payment_orders_2", "payment_orders", ["owner_user_id", "unresolved_binding_id"]
    )


def upgrade():
    for name in ("cancel_requested_at", "cancel_after", "cancelled_at"):
        op.add_column("payment_orders", sa.Column(name, mysql.DATETIME(fsp=6)))
    replace_slot(True)
    op.create_index("ix_payment_cancel", "payment_orders", ["cancelled_at", "cancel_after"])


def downgrade():
    # 取消后可能已有新订单，旧槽位唯一性无法安全恢复；仅支持向前修复。
    raise RuntimeError("支付取消迁移不支持自动降级，请使用经验证的备份恢复")
