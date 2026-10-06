"""R4本域归档目录与永久冷去重标识。"""

import sqlalchemy as sa
from alembic import op

from services.common import archive_schema_v1

revision = "room_0008"
down_revision = "room_0007"
branch_labels = None
depends_on = None


def upgrade():
    archive_schema_v1.upgrade(op)
    op.add_column("room_operations", sa.Column("balance_result", sa.JSON(), nullable=True))


def downgrade():
    archive_schema_v1.downgrade(op)

