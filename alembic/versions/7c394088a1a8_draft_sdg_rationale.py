"""draft sdg rationale

Adds drafts.sdg_rationale -- one sentence on why the classifier picked
that goal. Nullable: drafts classified before this migration keep a bare
goal + keyword with no explanation, which is exactly what the column
means (unknown), not a defect to backfill.

Revision ID: 7c394088a1a8
Revises: f87c37b6b57e
Create Date: 2026-08-03 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7c394088a1a8'
down_revision: Union[str, None] = 'f87c37b6b57e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('drafts', sa.Column('sdg_rationale', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('drafts', 'sdg_rationale')
