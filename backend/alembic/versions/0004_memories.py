"""memories — mémoire longue de l'agent (pgvector, étape 3.2)."""

from alembic import op

revision = "0004_memories"
down_revision = "0003_evals"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""
        CREATE TABLE memories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            content TEXT NOT NULL,
            embedding vector({EMBEDDING_DIM}) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_memories_embedding ON memories "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memories")
