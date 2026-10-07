"""R4本域归档目录与永久冷去重标识。"""

from alembic import op

from services.common import archive_schema_v1

revision = "school_0008"
down_revision = "school_0007"
branch_labels = None
depends_on = None


def upgrade():
    archive_schema_v1.upgrade(op)


def downgrade():
    archive_schema_v1.downgrade(op)
