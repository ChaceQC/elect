"""T3 每用户串行凭据控制与可恢复撤回。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "identity_0003"
down_revision = "identity_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("credential_version", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("credential_status", sa.String(32), nullable=True))
    op.add_column("users", sa.Column("credential_operation_id", mysql.BINARY(16), nullable=True))
    op.create_unique_constraint(
        "uq_credential_revoke_version",
        "credential_operations",
        ["owner_user_id", "expected_credential_version"],
    )


def downgrade():
    op.drop_constraint("uq_credential_revoke_version", "credential_operations", type_="unique")
    for name in ["credential_operation_id", "credential_status", "credential_version"]:
        op.drop_column("users", name)
