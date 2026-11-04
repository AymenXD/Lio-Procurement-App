"""Tenant booking rules: deterministic, enforced by the server, so neither AI nor users can
bypass them (e.g. Acme: cable ties → Electrical Engineering, whatever else is chosen)."""

import re
import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Organization
from app.schemas.organizations import BookingRule, OrganizationSettings

# A rule decides the request's group only if its lines are at least half of the request's
# value, so a $20 box of cable ties doesn't re-book a $5,000 moss wall.
MIN_VALUE_SHARE = Decimal("0.5")

Line = tuple[str, Decimal]  # (description, line total)


def mentions(text: str, keyword: str) -> bool:
    """Whole-word match, case-insensitive, plural allowed: "toner" matches "Toners HP 305"."""
    words = r"[\s-]+".join(re.escape(w) for w in keyword.split())
    return re.search(rf"\b{words}s?\b", text, re.IGNORECASE) is not None


def match_rule(lines: list[Line], rules: list[BookingRule]) -> BookingRule | None:
    """The rule whose matching lines carry the most value (ties: first rule listed).

    A rule with ``max_total`` applies only if the request total is below it.
    """
    total = sum((amount for _, amount in lines), Decimal(0))
    best: BookingRule | None = None
    best_value = Decimal(-1)
    for rule in rules:
        if rule.max_total is not None and total >= Decimal(str(rule.max_total)):
            continue
        matching = [
            amount for text, amount in lines if any(mentions(text, k) for k in rule.keywords)
        ]
        if not matching:
            continue
        value = sum(matching, Decimal(0))
        if total > 0 and value / total < MIN_VALUE_SHARE:
            continue
        if value > best_value:
            best, best_value = rule, value
    return best


def rules_for(db: Session, organization_id: uuid.UUID | None) -> list[BookingRule]:
    """The organisation's rules (none for unknown orgs)."""
    org = db.get(Organization, organization_id) if organization_id else None
    return OrganizationSettings(**(org.settings or {})).booking_rules if org else []
