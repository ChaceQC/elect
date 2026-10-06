"""手动请求预算索引；旧七天有效期由维护入口按创建时间延长。"""

from alembic import op

revision = "monitoring_0007"
down_revision = "monitoring_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_monitor_requests_budget", "monitor_run_requests",
                    ["owner_user_id", "created_at"])


def downgrade():
    op.drop_index("ix_monitor_requests_budget", table_name="monitor_run_requests")
