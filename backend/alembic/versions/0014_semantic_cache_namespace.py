"""semantic_cache.namespace — isolation cross-user du cache (étape 23g, CVE-2026-89032).

Chaque entrée du cache sémantique porte un namespace (défaut 'default') ;
lookup/store filtrent dessus, donc aucune fuite entre namespaces. En v1 le
namespace est celui du déploiement (config SEMANTIC_CACHE_NAMESPACE).
"""

from alembic import op

revision = "0014_semantic_cache_namespace"
down_revision = "0013_run_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE semantic_cache "
        "ADD COLUMN namespace TEXT NOT NULL DEFAULT 'default'"
    )
    op.execute("CREATE INDEX ix_semantic_cache_namespace ON semantic_cache (namespace)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_semantic_cache_namespace")
    op.execute("ALTER TABLE semantic_cache DROP COLUMN IF EXISTS namespace")
