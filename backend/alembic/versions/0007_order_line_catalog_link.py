"""link order lines to catalog articles

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-04

Records which catalog article an order line uses and the quoted unit price it
replaced, so negotiated-price usage and savings can be measured. Both columns are
nullable: lines typed by hand or extracted from a quote have no article.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("order_lines", sa.Column("article_id", sa.Uuid(), nullable=True))
    op.add_column(
        "order_lines", sa.Column("quoted_unit_price", sa.Numeric(12, 2), nullable=True)
    )
    # Deleting an article keeps the line (its price is already stored), just unlinked.
    op.create_foreign_key(
        "fk_order_lines_article_id",
        "order_lines",
        "articles",
        ["article_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_order_lines_article_id", "order_lines", ["article_id"])


def downgrade() -> None:
    op.drop_index("ix_order_lines_article_id", table_name="order_lines")
    op.drop_constraint("fk_order_lines_article_id", "order_lines", type_="foreignkey")
    op.drop_column("order_lines", "quoted_unit_price")
    op.drop_column("order_lines", "article_id")
