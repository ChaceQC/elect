"""T3 保留加密账号展示值，独立保存撤销台账，不保留撤销密码。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "school_0003"
down_revision = "school_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "school_credentials", sa.Column("account_display", mysql.LONGBLOB(), nullable=True)
    )
    op.create_table(
        "credential_revocations",
        sa.Column("id", mysql.BINARY(16), primary_key=True),
        sa.Column("owner_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("credential_ref", mysql.BINARY(16), nullable=False),
        sa.Column("credential_version", sa.BigInteger(), nullable=False),
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
        sa.CheckConstraint("credential_version>=1", name="ck_revocation_version"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )


def downgrade():
    op.drop_table("credential_revocations")
    op.drop_column("school_credentials", "account_display")
