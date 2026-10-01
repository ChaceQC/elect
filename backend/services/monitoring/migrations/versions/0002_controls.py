"""T3 持久控制请求、凭据屏障和偏好版本。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "monitoring_0002"
down_revision = "monitoring_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("monitors", sa.Column("preference_version", sa.BigInteger(), nullable=True))
    op.add_column("monitors", sa.Column("credential_operation_id", mysql.BINARY(16), nullable=True))
    op.add_column(
        "monitors",
        sa.Column("credential_allowed", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "control_operations", sa.Column("request_digest", mysql.BINARY(32), nullable=True)
    )
    op.add_column(
        "control_operations", sa.Column("previous_binding_id", mysql.BINARY(16), nullable=True)
    )
    op.add_column(
        "control_operations", sa.Column("credential_version", sa.BigInteger(), nullable=True)
    )


def downgrade():
    for column in ["credential_version", "previous_binding_id", "request_digest"]:
        op.drop_column("control_operations", column)
    for column in ["credential_allowed", "credential_operation_id", "preference_version"]:
        op.drop_column("monitors", column)
