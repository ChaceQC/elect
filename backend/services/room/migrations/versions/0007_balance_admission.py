"""余额系统来源独立计额；沿用请求键唯一约束。"""

import sqlalchemy as sa
from alembic import op

revision = "room_0007"
down_revision = "room_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("room_operations", sa.Column("request_source", sa.String(16),
                                              nullable=False, server_default="browser"))
    op.create_index("ix_room_balance_budget", "room_operations",
                    ["owner_user_id", "type", "request_source", "created_at"])
    op.create_index("ix_room_balance_pending", "room_operations",
                    ["owner_user_id", "type", "request_source", "state"])


def downgrade():
    op.drop_index("ix_room_balance_pending", table_name="room_operations")
    op.drop_index("ix_room_balance_budget", table_name="room_operations")
    op.drop_column("room_operations", "request_source")
