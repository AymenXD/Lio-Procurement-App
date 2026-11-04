"""Unit tests for the number checks. Figures are taken from the Acme quotes."""

from app.schemas.extraction import ExtractedVendorData
from app.services.reconciliation import check_line, check_numbers, check_total


def _quote(lines: list[tuple[float, float, float]], tax: float, total: float):
    return ExtractedVendorData.model_validate({
        "orderLines": [{"amount": a, "unitPrice": p, "totalPrice": t} for a, p, t in lines],
        "taxAmount": tax,
        "totalCost": total,
    })


def test_correct_quote_has_no_warnings():
    # Verdeform: 15.75 × 7.65 = 120.4875, printed as 120.49 (rounding is fine).
    verdeform = _quote(
        [(13.78, 52.00, 716.56), (15.75, 7.65, 120.49), (1, 350.00, 350.00), (1, 113.85, 113.85)],
        tax=112.20, total=1413.10,
    )
    assert check_numbers(verdeform) == []


def test_wrong_line_total_is_flagged():
    assert check_line(2, 1, 622.00, 650.00) == (
        "Line 2: 1 × 622.00 = 622.00, but the line total is 650.00"
    )


def test_lines_not_adding_up_to_total_is_flagged():
    # Greenmantle with the alternative item (430.00) wrongly counted as a line.
    assert check_total([715.26, 622.00, 430.00, 215.00], 133.88, 1686.14) == (
        "Lines + tax = 2,116.14, but the quote total is 1,686.14"
    )


def test_missing_values_skip_the_check():
    assert check_line(1, 1, 0, 715.26) is None  # unit price missing
    assert check_total([715.26], 0, 0) is None  # total missing
