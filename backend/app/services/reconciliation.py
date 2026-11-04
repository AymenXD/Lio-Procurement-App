"""Deterministic number checks on an extracted quote. They warn; they never fail an upload."""

from decimal import ROUND_HALF_UP, Decimal

from app.schemas.extraction import ExtractedVendorData

CENT = Decimal("0.01")


def _money(value: float) -> Decimal:
    return Decimal(str(value))


def _fmt(value: Decimal) -> str:
    return f"{value:,.2f}"


def check_line(index: int, amount: float, unit_price: float, total_price: float) -> str | None:
    """Warn if quantity × unit price differs from the line total by more than a cent."""
    if not (amount and unit_price and total_price):
        return None  # a missing value is already flagged as a missing field
    expected = (_money(amount) * _money(unit_price)).quantize(CENT, ROUND_HALF_UP)
    if abs(expected - _money(total_price)) <= CENT:
        return None
    return (
        f"Line {index}: {amount:g} × {_fmt(_money(unit_price))} = {_fmt(expected)}, "
        f"but the line total is {_fmt(_money(total_price))}"
    )


def check_total(line_totals: list[float], tax_amount: float, total_cost: float) -> str | None:
    """Warn if the lines plus tax differ from the quote's grand total by more than a cent."""
    if not (line_totals and total_cost):
        return None
    computed = sum((_money(t) for t in line_totals), Decimal(0)) + _money(tax_amount)
    if abs(computed - _money(total_cost)) <= CENT:
        return None
    return f"Lines + tax = {_fmt(computed)}, but the quote total is {_fmt(_money(total_cost))}"


def check_numbers(data: ExtractedVendorData) -> list[str]:
    """All warnings for one quote."""
    warnings = [
        check_line(i, line.amount, line.unit_price, line.total_price)
        for i, line in enumerate(data.order_lines, start=1)
    ]
    warnings.append(
        check_total([line.total_price for line in data.order_lines], data.tax_amount,
                    data.total_cost)
    )
    return [w for w in warnings if w]
