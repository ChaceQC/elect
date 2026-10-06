"""R4本域归档目录与永久冷去重标识。"""

from alembic import op

from services.common import archive_schema_v1

revision = "notification_0003"
down_revision = "notification_0002"
branch_labels = None
depends_on = None


def upgrade():
    archive_schema_v1.upgrade(op)


def downgrade():
    archive_schema_v1.downgrade(op)

