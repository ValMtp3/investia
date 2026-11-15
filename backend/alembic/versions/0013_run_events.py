"""run_events — journal des événements SSE par run (replay Last-Event-ID, étape 23f).

Chaque événement émis sur POST /agent/run est persisté avec un seq croissant par
run ; à la reconnexion (header Last-Event-ID + run_id dans le body), le serveur
renvoie les événements manqués (seq > last) avec leur id d'origine.
"""

from alembic import op

revision = "0013_run_events"
down_revision = "0012_router_linucb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE run_events (
            run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL,
            event TEXT NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, seq)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS run_events")
