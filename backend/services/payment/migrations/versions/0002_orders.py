"""T6 持久订单控制与二维码状态。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "payment_0002"
down_revision = "payment_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payment_owners",
        sa.Column("owner_user_id", mysql.BINARY(16), primary_key=True),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    for column in [
        sa.Column("qr_status", sa.String(32), nullable=False, server_default="not_requested"),
        sa.Column("qr_error_code", sa.String(64)),
        sa.Column("qr_expires_at", mysql.DATETIME(fsp=6)),
        sa.Column("next_check_at", mysql.DATETIME(fsp=6)),
        sa.Column("check_lease_owner", sa.String(128)),
        sa.Column("check_lease_until", mysql.DATETIME(fsp=6)),
        sa.Column(
            "balance_refresh_state", sa.String(32), nullable=False, server_default="not_required"
        ),
        sa.Column("balance_refresh_operation_id", mysql.BINARY(16)),
    ]:
        op.add_column("payment_orders", column)
    op.create_index(
        "ix_payment_orders_check", "payment_orders", ["next_check_at", "check_lease_until"]
    )
    op.add_column(
        "payment_operations",
        sa.Column(
            "open_order_id",
            mysql.BINARY(16),
            sa.Computed(
                "IF(state IN ('accepted','running','reconciling','unknown'), order_id, NULL)",
                persisted=True,
            ),
        ),
    )
    op.create_unique_constraint(
        "uq_payment_open_operation", "payment_operations", ["open_order_id"]
    )


def downgrade():
    op.drop_constraint("uq_payment_open_operation", "payment_operations", type_="unique")
    op.drop_column("payment_operations", "open_order_id")
    op.drop_index("ix_payment_orders_check", table_name="payment_orders")
    for name in [
        "qr_status",
        "qr_error_code",
        "qr_expires_at",
        "next_check_at",
        "check_lease_owner",
        "check_lease_until",
        "balance_refresh_state",
        "balance_refresh_operation_id",
    ]:
        op.drop_column("payment_orders", name)
    op.drop_table("payment_owners")
