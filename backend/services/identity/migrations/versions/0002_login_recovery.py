"""T2 持久登录恢复元数据；不包含明文学号、密码或 token。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "identity_0002"
down_revision = "identity_0001"
branch_labels = None
depends_on = None


def upgrade():
    columns = [
        sa.Column("challenge_hash", mysql.BINARY(32), nullable=True),
        sa.Column("request_digest", mysql.BINARY(32), nullable=True),
        sa.Column("expected_user_id", mysql.BINARY(16), nullable=True),
        sa.Column("credential_version", sa.BigInteger(), nullable=True),
        sa.Column("expected_credential_version", sa.BigInteger(), nullable=True),
        sa.Column("agreement_version", sa.String(64), nullable=True),
        sa.Column("content_hash", mysql.BINARY(32), nullable=True),
        sa.Column("credential_use_allowed", sa.Boolean(), nullable=True),
        sa.Column("next_reconcile_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("issued_session_id", mysql.BINARY(16), nullable=True),
    ]
    for column in columns:
        op.add_column("login_attempts", column)
    op.create_unique_constraint("uq_login_attempt_challenge", "login_attempts", ["challenge_hash"])


def downgrade():
    op.drop_constraint("uq_login_attempt_challenge", "login_attempts", type_="unique")
    for name in [
        "issued_session_id",
        "next_reconcile_at",
        "credential_use_allowed",
        "content_hash",
        "agreement_version",
        "expected_credential_version",
        "credential_version",
        "expected_user_id",
        "request_digest",
        "challenge_hash",
    ]:
        op.drop_column("login_attempts", name)
