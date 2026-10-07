"""按owner/绑定/电表key定位更早观测，保留原时间分页索引。"""

from alembic import op

revision = "monitoring_0010"
down_revision = "monitoring_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_sample_meter_lookup", "monitor_samples",
                    ["owner_user_id", "binding_id", "meter_source_record_key", "captured_at", "id"])


def downgrade():
    op.drop_index("ix_sample_meter_lookup", table_name="monitor_samples")
