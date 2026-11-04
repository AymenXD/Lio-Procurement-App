"""Server-side money math: the browser's totals are never trusted."""

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def line_total(unit_price: float | Decimal, amount: float | Decimal) -> Decimal:
    """Quantity × unit price, rounded to the cent."""
    return (Decimal(str(unit_price)) * Decimal(str(amount))).quantize(CENT, ROUND_HALF_UP)


def request_total(line_totals: Iterable[float | Decimal], tax: float | Decimal | None) -> Decimal:
    """Sum of the lines plus tax: what the quote's total says and what Acme pays."""
    lines = sum((Decimal(str(t)) for t in line_totals), Decimal("0"))
    return (lines + Decimal(str(tax or 0))).quantize(CENT, ROUND_HALF_UP)
