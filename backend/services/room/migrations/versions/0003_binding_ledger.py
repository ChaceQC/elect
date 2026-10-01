"""T3 绑定候选、凭据快照、确认事实与默认子操作。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "room_0003"
down_revision = "room_0002"
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column("candidate_id", sa.String(128, collation="utf8mb4_bin"), nullable=True),
        sa.Column("credential_ref", mysql.BINARY(16), nullable=True),
        sa.Column("credential_version", sa.BigInteger(), nullable=True),
        sa.Column("binding_status", sa.String(32), nullable=True),
        sa.Column("default_status", sa.String(32), nullable=True),
        sa.Column("default_operation_id", mysql.BINARY(16), nullable=True),
    ]:
        op.add_column("room_operations", column)
    op.create_check_constraint(
        "ck_room_binding_status",
        "room_operations",
        "binding_status IN ('pending','confirmed','failed','unknown')",
    )
    op.create_check_constraint(
        "ck_room_default_status",
        "room_operations",
        "default_status IN ('pending','switching','confirmed','unchanged','failed')",
    )
    op.create_check_constraint(
        "ck_room_credential_version", "room_operations", "credential_version >= 1"
    )
    op.create_foreign_key(
        "fk_room_default_operation",
        "room_operations",
        "room_operations",
        ["default_operation_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint("fk_room_default_operation", "room_operations", type_="foreignkey")
    for name in ["ck_room_credential_version", "ck_room_default_status", "ck_room_binding_status"]:
        op.drop_constraint(name, "room_operations", type_="check")
    for name in [
        "default_operation_id",
        "default_status",
        "binding_status",
        "credential_version",
        "credential_ref",
        "candidate_id",
    ]:
        op.drop_column("room_operations", name)
