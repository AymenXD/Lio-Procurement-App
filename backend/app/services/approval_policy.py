"""Auto-approval: small requests skip the buyer (Acme: under $2,000)."""

import uuid
from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Organization
from app.schemas.organizations import AutoApprovalPolicy, OrganizationSettings

# Edits that change what is bought, from whom, or for how much. They void an approval.
MATERIAL_FIELDS = frozenset({"vendor_name", "vat_id", "order_lines", "tax_amount", "total_cost"})


def auto_approves(total: Decimal, policy: AutoApprovalPolicy) -> bool:
    """Strictly below the limit: a request of exactly $2,000.00 still needs a buyer."""
    return policy.enabled and total < Decimal(str(policy.below_amount))


def needs_reapproval(changed_fields: Iterable[str]) -> bool:
    return not MATERIAL_FIELDS.isdisjoint(changed_fields)


def policy_for(db: Session, organization_id: uuid.UUID | None) -> AutoApprovalPolicy:
    """The organisation's policy; off when it has none."""
    org = db.get(Organization, organization_id) if organization_id else None
    return OrganizationSettings(**((org.settings if org else None) or {})).auto_approval
