"""request tax amount and approval source

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-04

tax_amount: stored so the server can compute total_cost = sum of lines + tax.
approval_source: "auto" (approved by the organisation's policy) or "manual" (a buyer),
so auto-approvals are visible and countable. Existing decisions were made by people.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "procurement_requests", sa.Column("tax_amount", sa.Numeric(12, 2), nullable=True)
    )
    op.add_column(
        "procurement_requests", sa.Column("approval_source", sa.String(), nullable=True)
    )
    op.create_check_constraint(
        "ck_procurement_request_approval_source",
        "procurement_requests",
        "approval_source IS NULL OR approval_source IN ('auto', 'manual')",
    )
    op.execute(
        "UPDATE procurement_requests SET approval_source = 'manual' "
        "WHERE approval_status <> 'pending'"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_procurement_request_approval_source", "procurement_requests", type_="check"
    )
    op.drop_column("procurement_requests", "approval_source")
    op.drop_column("procurement_requests", "tax_amount")
