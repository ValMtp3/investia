"""Spans OpenTelemetry GenAI vers PostgreSQL — otel_spans (étape 9, D38)."""

from alembic import op

revision = "0006_otel_spans"
down_revision = "0005_portfolio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE otel_spans (
            id BIGSERIAL PRIMARY KEY,
            span_id TEXT NOT NULL,
            trace_id TEXT NOT NULL,
            parent_span_id TEXT,
            run_id UUID REFERENCES runs(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            start_ts TIMESTAMPTZ NOT NULL,
            end_ts TIMESTAMPTZ,
            attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'UNSET',
            error TEXT
        )
        """
    )
    op.execute("CREATE INDEX idx_otel_spans_run_id ON otel_spans (run_id)")
    op.execute("CREATE INDEX idx_otel_spans_trace_id ON otel_spans (trace_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS otel_spans")
