"""T6 学校订单密文与每个支付表单一次发送。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "school_0006"
down_revision = "school_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "adapter_payment_orders",
        sa.Column("order_id", mysql.BINARY(16), primary_key=True),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("binding_id", mysql.BINARY(16), nullable=False),
        sa.Column("upstream_operation_id", mysql.BINARY(16), nullable=False),
        sa.Column("credential_ref", mysql.BINARY(16), nullable=False),
        sa.Column("credential_version", sa.BigInteger(), nullable=False),
        sa.Column("payload_ciphertext", mysql.LONGBLOB(), nullable=False),
        sa.Column("observation_ciphertext", mysql.LONGBLOB()),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.UniqueConstraint("upstream_operation_id", name="uq_adapter_payment_upstream"),
        sa.ForeignKeyConstraint(
            ["upstream_operation_id"], ["upstream_operations.id"], ondelete="RESTRICT"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    for column in [
        sa.Column("flow_step", sa.String(8), nullable=False, server_default="E01"),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_until", mysql.DATETIME(fsp=6)),
        sa.Column("qr_ciphertext", mysql.LONGBLOB()),
        sa.Column("qr_mime", sa.String(32)),
    ]:
        op.add_column("payment_sessions", column)


def downgrade():
    for name in ["flow_step", "lease_owner", "lease_until", "qr_ciphertext", "qr_mime"]:
        op.drop_column("payment_sessions", name)
    op.drop_table("adapter_payment_orders")
