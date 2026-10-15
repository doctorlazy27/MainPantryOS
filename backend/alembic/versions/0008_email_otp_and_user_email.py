"""Add verified user email and OTP recovery.

Revision ID: 0008_email_otp_and_user_email
Revises: 0007_shelf_metadata
"""
from alembic import op


revision = "0008_email_otp_and_user_email"
down_revision = "0007_shelf_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255)")
    op.execute("ALTER TABLE registration_requests ADD COLUMN IF NOT EXISTS email VARCHAR(255)")
    op.execute("UPDATE users SET email = username || '@pending.local' WHERE email IS NULL")
    op.execute("UPDATE registration_requests SET email = username || '@pending.local' WHERE email IS NULL")
    op.execute("ALTER TABLE users ALTER COLUMN email SET NOT NULL")
    op.execute("ALTER TABLE registration_requests ALTER COLUMN email SET NOT NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_unique ON users (email)")
    op.execute("CREATE TABLE IF NOT EXISTS auth_otps (otp_id SERIAL PRIMARY KEY, email VARCHAR(255) NOT NULL, purpose VARCHAR(30) NOT NULL, code_hash VARCHAR(255) NOT NULL, expires_at TIMESTAMP NOT NULL, consumed_at TIMESTAMP NULL, attempts INTEGER NOT NULL DEFAULT 0)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_auth_otps_email ON auth_otps (email)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth_otps")
    op.execute("ALTER TABLE registration_requests DROP COLUMN IF EXISTS email")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email")