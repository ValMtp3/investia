"""memories temporelles — valid_from/valid_until/superseded_by (étape 16a).

Soft delete uniquement : aucune ligne n'est jamais supprimée, l'oubli/archive
passe par valid_until. Index HNSW partiel sur les souvenirs courants only.
"""

from alembic import op

revision = "0009_temporal_memories"
down_revision = "0008_router_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE memories "
        "ADD COLUMN valid_from TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "ADD COLUMN valid_until TIMESTAMPTZ NULL, "
        "ADD COLUMN superseded_by UUID NULL REFERENCES memories(id), "
        "ADD COLUMN provenance TEXT NOT NULL DEFAULT 'agent', "
        "ADD COLUMN scope TEXT NOT NULL DEFAULT 'global'"
    )
    # Le recall ne scanne que les souvenirs courants (valid_until IS NULL).
    op.execute(
        "CREATE INDEX ix_memories_current_embedding ON memories "
        "USING hnsw (embedding vector_cosine_ops) WHERE valid_until IS NULL"
    )
    op.execute("CREATE INDEX ix_memories_valid_from ON memories (valid_from)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memories_valid_from")
    op.execute("DROP INDEX IF EXISTS ix_memories_current_embedding")
    op.execute(
        "ALTER TABLE memories "
        "DROP COLUMN scope, "
        "DROP COLUMN provenance, "
        "DROP COLUMN superseded_by, "
        "DROP COLUMN valid_until, "
        "DROP COLUMN valid_from"
    )
