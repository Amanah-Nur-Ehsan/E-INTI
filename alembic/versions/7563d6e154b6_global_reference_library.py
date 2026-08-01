"""global reference library

Drops reference_papers.project_id: the library becomes one shared pool
every draft queries, instead of a copy re-imported and re-enriched per
project. Before dropping the column, references that were imported into
more than one project (the same DOI/EID under different project_ids)
are deduplicated -- otherwise collapsing project_id would violate the
new global unique indexes on doi/scopus_eid.

Winner selection per duplicate group: prefer the row that already has an
embedding, then the row that has an abstract, then the oldest row. Child
tables (citation_recommendations, accepted_citations,
llm_verification_cache) are repointed to the winner, with any resulting
conflict against an existing winner-row deleted first -- each of those
tables carries its own unique constraint that a naive UPDATE could
violate.

Revision ID: 7563d6e154b6
Revises: cb91d38f0d36
Create Date: 2026-08-01 21:20:59.811396

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7563d6e154b6'
down_revision: Union[str, None] = 'cb91d38f0d36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Build the loser -> winner map for every duplicate group, by DOI
    #    first and then by scopus_eid (skipping anything DOI already
    #    resolved). Case-insensitive on DOI since imports don't reliably
    #    lowercase it.
    op.execute(
        """
        CREATE TEMP TABLE ref_dedupe (
            loser_id uuid PRIMARY KEY,
            winner_id uuid NOT NULL
        )
        """
    )

    op.execute(
        """
        INSERT INTO ref_dedupe (loser_id, winner_id)
        SELECT r.id, w.id
        FROM reference_papers r
        JOIN LATERAL (
            SELECT r2.id
            FROM reference_papers r2
            WHERE lower(r2.doi) = lower(r.doi)
            ORDER BY (r2.embedding IS NOT NULL) DESC,
                     (r2.abstract IS NOT NULL) DESC,
                     r2.created_at ASC,
                     r2.id ASC
            LIMIT 1
        ) w ON TRUE
        WHERE r.doi IS NOT NULL
          AND w.id <> r.id
        """
    )

    op.execute(
        """
        INSERT INTO ref_dedupe (loser_id, winner_id)
        SELECT r.id, w.id
        FROM reference_papers r
        JOIN LATERAL (
            SELECT r2.id
            FROM reference_papers r2
            WHERE r2.scopus_eid = r.scopus_eid
            ORDER BY (r2.embedding IS NOT NULL) DESC,
                     (r2.abstract IS NOT NULL) DESC,
                     r2.created_at ASC,
                     r2.id ASC
            LIMIT 1
        ) w ON TRUE
        WHERE r.scopus_eid IS NOT NULL
          AND w.id <> r.id
          AND NOT EXISTS (SELECT 1 FROM ref_dedupe d WHERE d.loser_id = r.id)
        """
    )

    # 2. Repoint child rows to the winner, deleting first wherever
    #    repointing would collide with a row the winner already has.
    op.execute(
        """
        DELETE FROM citation_recommendations c USING ref_dedupe d
        WHERE c.reference_id = d.loser_id
          AND EXISTS (
              SELECT 1 FROM citation_recommendations c2
              WHERE c2.claim_id = c.claim_id AND c2.reference_id = d.winner_id
          )
        """
    )
    op.execute(
        """
        UPDATE citation_recommendations c
        SET reference_id = d.winner_id
        FROM ref_dedupe d
        WHERE c.reference_id = d.loser_id
        """
    )

    op.execute(
        """
        DELETE FROM accepted_citations a USING ref_dedupe d
        WHERE a.reference_id = d.loser_id
          AND EXISTS (
              SELECT 1 FROM accepted_citations a2
              WHERE a2.claim_id = a.claim_id AND a2.reference_id = d.winner_id
          )
        """
    )
    op.execute(
        """
        UPDATE accepted_citations a
        SET reference_id = d.winner_id
        FROM ref_dedupe d
        WHERE a.reference_id = d.loser_id
        """
    )

    # llm_verification_cache was already fully cleared in the previous
    # migration (claim_hash now hashes the sentence, not the paraphrase),
    # so there is nothing meaningful left in it to repoint -- but delete
    # defensively in case anything was written between migrations.
    op.execute(
        """
        DELETE FROM llm_verification_cache v USING ref_dedupe d
        WHERE v.reference_id = d.loser_id
        """
    )

    # 3. Drop the now-unreferenced duplicate rows.
    op.execute(
        """
        DELETE FROM reference_papers r USING ref_dedupe d
        WHERE r.id = d.loser_id
        """
    )

    # 4. Drop the project-scoped shape, install the global one.
    op.drop_index('uq_reference_papers_project_id_doi', table_name='reference_papers')
    op.drop_index('uq_reference_papers_project_id_scopus_eid', table_name='reference_papers')
    op.drop_index(op.f('ix_reference_papers_project_id'), table_name='reference_papers')
    op.drop_constraint(
        op.f('fk_reference_papers_project_id_projects'),
        'reference_papers',
        type_='foreignkey',
    )
    op.drop_column('reference_papers', 'project_id')

    op.create_index(
        'uq_reference_papers_doi', 'reference_papers', ['doi'],
        unique=True, postgresql_where=sa.text('doi IS NOT NULL'),
    )
    op.create_index(
        'uq_reference_papers_scopus_eid', 'reference_papers', ['scopus_eid'],
        unique=True, postgresql_where=sa.text('scopus_eid IS NOT NULL'),
    )


def downgrade() -> None:
    # Global dedupe cannot be un-merged -- the losing rows and their
    # original project associations are gone. Restore from a pg_dump
    # backup taken before this migration instead.
    raise NotImplementedError(
        "This migration is not reversible. Restore from the pre-migration "
        "pg_dump backup (see the simplification plan, Step 0) instead of "
        "downgrading."
    )
