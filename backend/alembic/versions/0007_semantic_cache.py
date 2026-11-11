"""semantic_cache — cache sémantique des réponses de l'agent (pgvector, étape 12e)."""

from alembic import op

revision = "0007_semantic_cache"
down_revision = "0006_otel_spans"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""
        CREATE TABLE semantic_cache (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            embedding vector({EMBEDDING_DIM}) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_semantic_cache_embedding ON semantic_cache "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS semantic_cache")
