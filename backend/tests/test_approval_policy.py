"""Unit tests for server-side totals and the auto-approval policy (pure functions)."""

from decimal import Decimal

from app.schemas.organizations import AutoApprovalPolicy
from app.services.approval_policy import auto_approves, needs_reapproval
from app.services.totals import line_total, request_total

ACME = AutoApprovalPolicy(enabled=True, below_amount=2000)


def test_line_total_is_quantity_times_price_in_cents():
    assert line_total(150, 10) == Decimal("1500.00")
    assert line_total(19.99, 3) == Decimal("59.97")
    assert line_total(0.125, 1) == Decimal("0.13")  # half up


def test_request_total_is_lines_plus_tax():
    # The Apple quote: MacBook + eWaste fee + tax.
    assert request_total([Decimal("1409.06"), Decimal("4.00")], 121.53) == Decimal("1534.59")
    assert request_total([Decimal("100")], None) == Decimal("100.00")


def test_limit_is_strict():
    assert auto_approves(Decimal("1999.99"), ACME)
    assert not auto_approves(Decimal("2000.00"), ACME)
    assert not auto_approves(Decimal("2042.15"), ACME)  # Hollis, tax included


def test_disabled_policy_never_approves():
    assert not auto_approves(Decimal("1"), AutoApprovalPolicy())


def test_only_money_or_vendor_changes_need_reapproval():
    assert not needs_reapproval(["title", "department", "requestor_name"])
    assert needs_reapproval(["vendor_name"])
    assert needs_reapproval(["title", "order_lines"])
    assert needs_reapproval(["tax_amount"])
