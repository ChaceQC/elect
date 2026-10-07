"""owner轮转有界回收索引。"""

from alembic import op

revision = "monitoring_0008"
down_revision = "monitoring_0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_snapshot_owner_expiry", "sample_snapshots",
                    ["owner_user_id", "expires_at", "id"])


def downgrade():
    op.drop_index("ix_snapshot_owner_expiry", table_name="sample_snapshots")
