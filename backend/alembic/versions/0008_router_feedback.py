"""router_feedback — feedbacks du routeur appris (pgvector, étape 12h)."""

from alembic import op

revision = "0008_router_feedback"
down_revision = "0007_semantic_cache"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""
        CREATE TABLE router_feedback (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            question TEXT NOT NULL,
            model TEXT NOT NULL,
            success BOOLEAN NOT NULL,
            embedding vector({EMBEDDING_DIM}) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_router_feedback_embedding ON router_feedback "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS router_feedback")
