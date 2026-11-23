"""Initial schema: all 20 TestPilot tables.

Revision ID: 0001
Revises:
Create Date: 2026-11-22

BASELINE MIGRATION. It builds the schema from the ORM metadata. That is fine for the
very first revision, but it means this file must be FROZEN once real data exists:
before shipping a Phase-2+ model change, replace the body below with explicit
`op.create_table(...)` calls (`alembic revision --autogenerate` against an empty DB
prints them) and put the change in a NEW revision. tests/test_migrations.py
(`test_models_match_migrated_schema`) fails if the models drift from migrations.
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.models import Base
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    from app.models import Base
    Base.metadata.drop_all(bind=op.get_bind())
