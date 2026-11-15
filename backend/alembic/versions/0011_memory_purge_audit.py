"""memory_purge_audit — audit des purges hard RGPD (étape 23e).

Quand un souvenir est purgé (suppression RÉELLE, droit à l'oubli), on garde
une trace d'audit : id du souvenir, contenu MASQUÉ (jamais en clair, même dans
l'audit), raison, date. La table memories, elle, perd la ligne.
"""

from alembic import op

revision = "0011_memory_purge_audit"
down_revision = "0010_agent_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE memory_purge_audit (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            memory_id UUID NOT NULL,
            content_redacted TEXT NOT NULL,
            reason TEXT NOT NULL,
            purged_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_memory_purge_audit_memory ON memory_purge_audit (memory_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_purge_audit")
