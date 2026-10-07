"""R4本域归档目录与永久冷去重标识。"""

from alembic import op

from services.common import archive_schema_v1

revision = "identity_0004"
down_revision = "identity_0003"
branch_labels = None
depends_on = None


def upgrade():
    archive_schema_v1.upgrade(op)
    op.create_index("ix_login_session_reference", "login_attempts", ["issued_session_id"])


def downgrade():
    archive_schema_v1.downgrade(op)
