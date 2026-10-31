"""baseline vide — l'étape 0 ne crée pas de schéma métier.

Alembic est la seule source du schéma : jamais de create_all.
"""

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
