"""drop projects table

Removes the last relic of the old per-project architecture: the shared
reference library already went global in the previous migration, and the
app is moving to a single-page model with drafts as the unit of work.
Drops the project_id FK+index from drafts, analysis_runs, and exports,
then drops the projects table itself.

Revision ID: 872a6c0468fa
Revises: 7563d6e154b6
Create Date: 2026-08-01 21:57:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '872a6c0468fa'
down_revision: Union[str, None] = '7563d6e154b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('fk_drafts_project_id_projects', 'drafts', type_='foreignkey')
    op.drop_index('ix_drafts_project_id', table_name='drafts')
    op.drop_column('drafts', 'project_id')

    op.drop_constraint(
        'fk_analysis_runs_project_id_projects', 'analysis_runs', type_='foreignkey'
    )
    op.drop_index('ix_analysis_runs_project_id', table_name='analysis_runs')
    op.drop_column('analysis_runs', 'project_id')

    op.drop_constraint('fk_exports_project_id_projects', 'exports', type_='foreignkey')
    op.drop_index('ix_exports_project_id', table_name='exports')
    op.drop_column('exports', 'project_id')

    op.drop_table('projects')


def downgrade() -> None:
    # projects rows (name/description/field_of_study/citation_style/owner_id)
    # and which project each draft/run/export belonged to are gone once
    # upgrade() runs. Restore from a pg_dump backup instead of downgrading.
    raise NotImplementedError(
        "This migration is not reversible. Restore from a pre-migration "
        "pg_dump backup instead of downgrading."
    )
