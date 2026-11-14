"""agent_feedback — feedbacks du routeur d'agents A2A (pgvector, étape 18a).

Même pattern que 0008_router_feedback : question + embedding 1536 + liste
d'agents utilisés + succès du run.
"""

from alembic import op

revision = "0010_agent_feedback"
down_revision = "0009_temporal_memories"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"""
        CREATE TABLE agent_feedback (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            question TEXT NOT NULL,
            agents TEXT NOT NULL,
            success BOOLEAN NOT NULL,
            embedding vector({EMBEDDING_DIM}) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_agent_feedback_embedding ON agent_feedback "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_feedback")
