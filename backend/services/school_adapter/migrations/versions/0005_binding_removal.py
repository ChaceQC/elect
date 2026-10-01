"""解绑与新增共用未解决目标约束，保存缺席确认时间。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "school_0005"
down_revision = "school_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_upstream_operations_0", "upstream_operations", type_="check")
    op.create_check_constraint(
        "ck_upstream_operations_0",
        "upstream_operations",
        "operation_type IN ('bind_room','unbind_room','create_order','E01','E02','E03','E04')",
    )
    op.drop_constraint("uq_upstream_binding_target", "upstream_operations", type_="unique")
    op.drop_column("upstream_operations", "open_binding_target")
    op.add_column(
        "upstream_operations",
        sa.Column(
            "open_binding_target",
            sa.String(128, collation="utf8mb4_bin"),
            sa.Computed(
                "IF(operation_type IN ('bind_room','unbind_room') AND state IN ('prepared','dispatched','reconciling','unknown'),target_ref,NULL)",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_upstream_binding_target",
        "upstream_operations",
        ["owner_user_id", "open_binding_target"],
    )
    op.add_column(
        "upstream_operations", sa.Column("absence_first_at", mysql.DATETIME(fsp=6), nullable=True)
    )


def downgrade():
    op.drop_column("upstream_operations", "absence_first_at")
    op.drop_constraint("uq_upstream_binding_target", "upstream_operations", type_="unique")
    op.drop_column("upstream_operations", "open_binding_target")
    op.add_column(
        "upstream_operations",
        sa.Column(
            "open_binding_target",
            sa.String(128, collation="utf8mb4_bin"),
            sa.Computed(
                "IF(operation_type='bind_room' AND state IN ('prepared','dispatched','reconciling','unknown'),target_ref,NULL)",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_upstream_binding_target",
        "upstream_operations",
        ["owner_user_id", "open_binding_target"],
    )
    op.drop_constraint("ck_upstream_operations_0", "upstream_operations", type_="check")
    op.create_check_constraint(
        "ck_upstream_operations_0",
        "upstream_operations",
        "operation_type IN ('bind_room','create_order','E01','E02','E03','E04')",
    )
