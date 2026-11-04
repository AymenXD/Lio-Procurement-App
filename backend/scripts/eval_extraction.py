"""Score PDF extraction against the five Acme quotes (manual tool, needs a real OpenAI key).

Run from lio-procurement-app/:
    docker compose run --rm -v ./backend:/app -v ../quotes:/quotes:ro backend \
        python -m scripts.eval_extraction /quotes

Prints a Markdown table (paste into the PR) and, below it, what we got for each failed check.
Only extracted fields are printed, never document text.
"""

import json
import re
import sys
from decimal import Decimal
from pathlib import Path

from app.db.session import SessionLocal
from app.services.extraction import extract_vendor_data
from app.services.pdf import extract_text

FIXTURE = Path(__file__).parent.parent / "tests" / "fixtures" / "quotes_expected.json"
CENT = Decimal("0.01")
CHECKS = ["OK", "Vendor", "Tax ID", "Lines", "Total", "Commodity"]


# --- comparison helpers -------------------------------------------------------------------


def digits(value: str | None) -> str:
    """Tax IDs are compared on digits only: "94-1985704" == "94 1985704"."""
    return re.sub(r"\D", "", value or "")


def same_name(got: str | None, expected: list[str]) -> bool:
    """Case- and punctuation-insensitive: "Hollis Greenscapes, Inc" == "hollis greenscapes inc"."""
    def norm(s: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", s.lower()).split())

    return bool(got) and norm(got) in {norm(e) for e in expected}


def money(value) -> Decimal:
    return Decimal(str(value))


def same_amounts(got: list, expected: list[str]) -> bool:
    """Same amounts in any order, each within one cent. Extra or missing lines fail."""
    if len(got) != len(expected):
        return False
    pairs = zip(sorted(map(money, got)), sorted(map(money, expected)))
    return all(abs(g - e) <= CENT for g, e in pairs)


# --- pipeline -----------------------------------------------------------------------------


def run_pipeline(pdf_bytes: bytes, db):
    """The code under test. Today: PDF -> text -> one AI call. Update when the flow changes."""
    return extract_vendor_data(extract_text(pdf_bytes), db)


def score(expected: dict, result) -> tuple[dict[str, bool], dict[str, object]]:
    """Return pass/fail per check, plus what we got for the failed ones."""
    data = result.data
    if not result.success or data is None:
        return {c: False for c in CHECKS}, {"error": result.error}

    got = {
        "Vendor": data.vendor_name,
        "Tax ID": data.vat_id,
        "Lines": [str(line.total_price) for line in data.order_lines],
        "Total": data.total_cost,
        "Commodity": data.commodity_group_id,
    }
    tax_ok = (
        digits(data.vat_id) == digits(expected["tax_id"]) if expected["tax_id"] else not data.vat_id
    )
    passed = {
        "OK": True,
        "Vendor": same_name(data.vendor_name, expected["vendor_names"]),
        "Tax ID": tax_ok,
        "Lines": same_amounts(got["Lines"], expected["line_totals"]),
        "Total": abs(money(data.total_cost) - money(expected["total"])) <= CENT,
        "Commodity": data.commodity_group_id in expected["commodity_group_ids"],
    }
    return passed, {k: v for k, v in got.items() if not passed[k]}


def main(quotes_dir: Path) -> None:
    quotes = json.loads(FIXTURE.read_text())["quotes"]
    rows, details, points = [], [], 0

    with SessionLocal() as db:
        for q in quotes:
            result = run_pipeline((quotes_dir / q["file"]).read_bytes(), db)
            passed, failed = score(q, result)
            points += sum(passed.values())
            rows.append(f"| {q['file'][:32]} | " + " | ".join(
                "✓" if passed[c] else "✗" for c in CHECKS) + " |")
            if failed:
                details.append(f"- **{q['file']}**: {failed}")

    print("| Quote | " + " | ".join(CHECKS) + " |")
    print("|---|" + "---|" * len(CHECKS))
    print("\n".join(rows))
    print(f"\n**Score: {points} / {len(quotes) * len(CHECKS)}**\n")
    print("\n".join(details))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/quotes"))
