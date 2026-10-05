"""快照成员摘要复用与创建预算；旧 token 保留至原 TTL。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "monitoring_0006"
down_revision = "monitoring_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sample_snapshots", sa.Column("membership_hash", mysql.BINARY(32)))
    op.create_index("ix_sample_snapshots_created", "sample_snapshots", ["owner_user_id", "created_at"])


def downgrade():
    op.drop_index("ix_sample_snapshots_created", table_name="sample_snapshots")
    op.drop_column("sample_snapshots", "membership_hash")
