"""T2 验证后账号占位、多版本别名与幂等激活所有者。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "school_0002"
down_revision = "school_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "school_credentials",
        sa.Column("use_allowed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("credential_staging", sa.Column("owner_user_id", mysql.BINARY(16), nullable=True))
    op.create_table(
        "account_reservations",
        sa.Column("school_id", sa.String(64), nullable=False),
        sa.Column("key_version", sa.String(64), nullable=False),
        sa.Column("lookup_hash", mysql.BINARY(32), nullable=False),
        sa.Column("credential_id", mysql.BINARY(16), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.PrimaryKeyConstraint("school_id", "key_version", "lookup_hash"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )


def downgrade():
    op.drop_table("account_reservations")
    op.drop_column("credential_staging", "owner_user_id")
    op.drop_column("school_credentials", "use_allowed")
