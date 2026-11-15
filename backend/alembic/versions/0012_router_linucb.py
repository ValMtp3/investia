"""router_linucb — état persistant du routeur LinUCB + coût des feedbacks (étape 23d).

Deux changements :
- `router_feedback` gagne `cost_cents` (NULL pour les lignes d'avant 0012) :
  le reward LinUCB intègre le coût réel du run (succès − pondération coût).
- nouvelle table `router_linucb` : par bras (small/large), la matrice A aplatie
  (d×d → d² double precision[]), le vecteur b, le compteur n. Pas de pgvector ici.
"""

from alembic import op

revision = "0012_router_linucb"
down_revision = "0011_memory_purge_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE router_feedback ADD COLUMN cost_cents DOUBLE PRECISION NULL"
    )
    op.execute(
        """
        CREATE TABLE router_linucb (
            arm TEXT PRIMARY KEY,
            a DOUBLE PRECISION[] NOT NULL,
            b DOUBLE PRECISION[] NOT NULL,
            n INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS router_linucb")
    op.execute("ALTER TABLE router_feedback DROP COLUMN IF EXISTS cost_cents")
