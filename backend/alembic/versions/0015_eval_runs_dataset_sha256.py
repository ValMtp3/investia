"""eval_runs.dataset_sha256 — pinning du dataset de cas (étape 23h).

Chaque run d'evals enregistre le sha256 du fichier YAML de cas utilisé, pour
reproduire exactement un benchmark (pattern Harbor/TB 4.1 : datasets pinnés
par version). NULL pour les runs d'avant 0015 (rétrocompatible).
"""

from alembic import op

revision = "0015_eval_runs_dataset_sha256"
down_revision = "0014_semantic_cache_namespace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE eval_runs ADD COLUMN dataset_sha256 TEXT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE eval_runs DROP COLUMN IF EXISTS dataset_sha256")
