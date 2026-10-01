"""学校解绑操作、同目标屏障与默认撤除槽。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "room_0004"
down_revision = "room_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_room_operations_0", "room_operations", type_="check")
    op.create_check_constraint(
        "ck_room_operations_0",
        "room_operations",
        "type IN ('binding_sync','bind_room','unbind_room','switch_default','balance_refresh','history_sync')",
    )
    op.drop_constraint("ck_room_binding_status", "room_operations", type_="check")
    op.create_check_constraint(
        "ck_room_binding_status",
        "room_operations",
        "binding_status IN ('pending','confirmed','removed','failed','unknown')",
    )
    op.drop_constraint("uq_room_operations_1", "room_operations", type_="unique")
    op.drop_column("room_operations", "open_binding_target")
    op.add_column(
        "room_operations",
        sa.Column(
            "open_binding_target",
            mysql.BINARY(16),
            sa.Computed(
                "IF(type IN ('bind_room','unbind_room') AND state IN ('accepted','running','reconciling','unknown'),target_room_id,NULL)",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_room_operations_1", "room_operations", ["owner_user_id", "open_binding_target"]
    )
    op.add_column(
        "room_operations",
        sa.Column("removal_was_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "room_preferences", sa.Column("removal_operation_id", mysql.BINARY(16), nullable=True)
    )
    op.create_foreign_key(
        "fk_room_removal_operation",
        "room_preferences",
        "room_operations",
        ["removal_operation_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint("fk_room_removal_operation", "room_preferences", type_="foreignkey")
    op.drop_column("room_preferences", "removal_operation_id")
    op.drop_column("room_operations", "removal_was_default")
    op.drop_constraint("uq_room_operations_1", "room_operations", type_="unique")
    op.drop_column("room_operations", "open_binding_target")
    op.add_column(
        "room_operations",
        sa.Column(
            "open_binding_target",
            mysql.BINARY(16),
            sa.Computed(
                "IF(type='bind_room' AND state IN ('accepted','running','reconciling','unknown'),target_room_id,NULL)",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_room_operations_1", "room_operations", ["owner_user_id", "open_binding_target"]
    )
    op.drop_constraint("ck_room_binding_status", "room_operations", type_="check")
    op.create_check_constraint(
        "ck_room_binding_status",
        "room_operations",
        "binding_status IN ('pending','confirmed','failed','unknown')",
    )
    op.drop_constraint("ck_room_operations_0", "room_operations", type_="check")
    op.create_check_constraint(
        "ck_room_operations_0",
        "room_operations",
        "type IN ('binding_sync','bind_room','switch_default','balance_refresh','history_sync')",
    )
