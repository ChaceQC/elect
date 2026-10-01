"""T4保存采集时的间隔，避免配置修改改变历史间隔质量。"""

import sqlalchemy as sa
from alembic import op

revision = "monitoring_0004"
down_revision = "monitoring_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "monitor_samples", sa.Column("capture_interval_minutes", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        "ck_sample_interval",
        "monitor_samples",
        "capture_interval_minutes IS NULL OR capture_interval_minutes BETWEEN 60 AND 1440",
    )


def downgrade():
    op.drop_constraint("ck_sample_interval", "monitor_samples", type_="check")
    op.drop_column("monitor_samples", "capture_interval_minutes")
