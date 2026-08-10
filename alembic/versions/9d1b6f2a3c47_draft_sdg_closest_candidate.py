"""draft sdg closest candidate

Adds drafts.sdg_closest_number/sdg_closest_name -- set only when the
classifier declines (sdg_number is null): the best-ranked candidate it
considered but judged not a genuine fit, shown to the user as an
unconfirmed "closest candidate" rather than a real classification.
Nullable: existing declined drafts simply have no closest candidate
recorded, which is the correct meaning (unknown), not a defect to
backfill.

Revision ID: 9d1b6f2a3c47
Revises: 7c394088a1a8
Create Date: 2026-08-10 22:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9d1b6f2a3c47'
down_revision: Union[str, None] = '7c394088a1a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('drafts', sa.Column('sdg_closest_number', sa.Integer(), nullable=True))
    op.add_column('drafts', sa.Column('sdg_closest_name', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('drafts', 'sdg_closest_name')
    op.drop_column('drafts', 'sdg_closest_number')
