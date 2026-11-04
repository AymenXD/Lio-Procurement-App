"""Unit tests for the booking rule engine (pure functions, no database)."""

from decimal import Decimal

from app.schemas.organizations import BookingRule
from app.services.booking_rules import match_rule, mentions

CABLE = BookingRule(id="cable", label="Cable ties", keywords=["cable tie", "zip tie"],
                    commodity_group_id=11)
TONER = BookingRule(id="toner", label="Printer toner", keywords=["toner"], commodity_group_id=29)
SOFTWARE = BookingRule(id="sw", label="Small software", keywords=["subscription", "saas"],
                       commodity_group_id=2001, max_total=2000)
RULES = [CABLE, TONER, SOFTWARE]


def _lines(*items: tuple[str, str]) -> list[tuple[str, Decimal]]:
    return [(text, Decimal(amount)) for text, amount in items]


def test_mentions_whole_words_and_plurals():
    assert mentions("Cable ties 200mm, black", "cable tie")
    assert mentions("HP 305 Toners", "toner")
    assert mentions("ZIP-TIE assortment", "zip tie")
    assert not mentions("Tonerless printer", "toner")


def test_each_rule_applies():
    assert match_rule(_lines(("Cable ties 200mm", "40")), RULES) is CABLE
    assert match_rule(_lines(("HP 305 black toner", "80")), RULES) is TONER
    assert match_rule(_lines(("Slack Pro subscription, annual", "960")), RULES) is SOFTWARE


def test_small_means_below_the_limit():
    assert match_rule(_lines(("Salesforce subscription, annual", "24000")), RULES) is None


def test_mixed_request_goes_to_the_rule_with_most_value():
    lines = _lines(("Cable ties", "50"), ("HP toner", "300"))
    assert match_rule(lines, RULES) is TONER


def test_minor_matching_line_does_not_rebook_the_request():
    # $20 of cable ties inside a $5,000 moss wall order: the wall decides the group.
    lines = _lines(("Moss wall", "5000"), ("Cable ties", "20"))
    assert match_rule(lines, RULES) is None


def test_no_rules_or_no_match():
    assert match_rule(_lines(("Moss wall", "5000")), RULES) is None
    assert match_rule(_lines(("HP toner", "80")), []) is None
