"""portefeuille simulé — portfolios, positions, orders, capital_adjustments (4.1)."""

from alembic import op

revision = "0005_portfolio"
down_revision = "0004_memories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE portfolios (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'EUR',
            cash NUMERIC(14,2) NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE positions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL,
            quantity NUMERIC(18,8) NOT NULL,
            avg_price NUMERIC(14,4) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (portfolio_id, symbol)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity NUMERIC(18,8) NOT NULL,
            price NUMERIC(14,4) NOT NULL,
            fee NUMERIC(14,2) NOT NULL,
            status TEXT NOT NULL DEFAULT 'simulated',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE capital_adjustments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
            amount NUMERIC(14,2) NOT NULL,
            reason TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS capital_adjustments")
    op.execute("DROP TABLE IF EXISTS orders")
    op.execute("DROP TABLE IF EXISTS positions")
    op.execute("DROP TABLE IF EXISTS portfolios")
