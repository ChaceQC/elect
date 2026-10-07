"""旧缓存保留未知序号，不伪造学校观测时间。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "room_0006"
down_revision = "room_0005"
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column("observation_sequence", sa.BigInteger()),
        sa.Column("observation_hash", mysql.BINARY(32)),
        sa.Column("last_success_sequence", sa.BigInteger()),
        sa.Column("last_error_sequence", sa.BigInteger()),
        sa.Column("last_error_at", mysql.DATETIME(fsp=6)),
        sa.Column("last_error_code", sa.String(64)),
    ]:
        op.add_column("room_balance_cache", column)


def downgrade():
    for name in ["last_error_code", "last_error_at", "last_error_sequence",
                 "last_success_sequence", "observation_hash", "observation_sequence"]:
        op.drop_column("room_balance_cache", name)
