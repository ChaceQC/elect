"""每个owner独立的持久余额观测序号，不复用凭据或监控版本。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "school_0007"
down_revision = "school_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "balance_observation_counters",
        sa.Column("owner_user_id", mysql.BINARY(16), primary_key=True),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )


def downgrade():
    op.drop_table("balance_observation_counters")
