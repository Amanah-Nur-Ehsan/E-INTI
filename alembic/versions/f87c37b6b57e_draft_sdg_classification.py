"""draft sdg classification

Adds sdg_number/sdg_name/sdg_keyword to drafts -- one SDG classified per
paper during analysis (app/services/sdg_classification_service.py).
All nullable: existing drafts and any run whose classification stage
hasn't executed yet simply have no SDG set.

Revision ID: f87c37b6b57e
Revises: 872a6c0468fa
Create Date: 2026-08-02 08:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f87c37b6b57e'
down_revision: Union[str, None] = '872a6c0468fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('drafts', sa.Column('sdg_number', sa.Integer(), nullable=True))
    op.add_column('drafts', sa.Column('sdg_name', sa.Text(), nullable=True))
    op.add_column('drafts', sa.Column('sdg_keyword', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('drafts', 'sdg_keyword')
    op.drop_column('drafts', 'sdg_name')
    op.drop_column('drafts', 'sdg_number')
