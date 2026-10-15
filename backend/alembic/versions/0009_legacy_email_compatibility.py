"""Allow legacy users without an email address.

Revision ID: 0009_legacy_email_compatibility
Revises: 0008_email_otp_and_user_email
"""
from alembic import op


revision = "0009_legacy_email_compatibility"
down_revision = "0008_email_otp_and_user_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN email DROP NOT NULL")
    op.execute("ALTER TABLE registration_requests ALTER COLUMN email DROP NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN email SET NOT NULL")
    op.execute("ALTER TABLE registration_requests ALTER COLUMN email SET NOT NULL")