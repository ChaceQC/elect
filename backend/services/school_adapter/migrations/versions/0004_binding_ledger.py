"""T3 单目标未解决屏障、加密候选与脱敏 B02 确认结果。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "school_0004"
down_revision = "school_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "upstream_operations",
        "target_ref",
        existing_type=sa.String(128),
        type_=sa.String(128, collation="utf8mb4_bin"),
        existing_nullable=False,
    )
    op.add_column(
        "upstream_operations", sa.Column("candidate_ciphertext", mysql.LONGBLOB(), nullable=True)
    )
    op.add_column("upstream_operations", sa.Column("confirmed_record", sa.JSON(), nullable=True))
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


def downgrade():
    op.drop_constraint("uq_upstream_binding_target", "upstream_operations", type_="unique")
    for name in ["open_binding_target", "confirmed_record", "candidate_ciphertext"]:
        op.drop_column("upstream_operations", name)
    op.alter_column(
        "upstream_operations",
        "target_ref",
        existing_type=sa.String(128),
        type_=sa.String(128),
        existing_nullable=False,
    )
