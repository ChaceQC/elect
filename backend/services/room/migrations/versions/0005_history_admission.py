"""历史同步受理速率索引；保留 operation 幂等记录。"""

from alembic import op

revision = "room_0005"
down_revision = "room_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_room_operations_admission", "room_operations", ["owner_user_id", "type", "created_at"]
    )


def downgrade():
    op.drop_index("ix_room_operations_admission", table_name="room_operations")
