"""Unit tests for catalog matching. Embeddings are faked; no real API calls."""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Article, CommodityGroup, Organization, Supplier
from app.schemas.articles import SuggestionLine
from app.services import catalog_matching as cm

IT_HARDWARE = 29

# Fake "meaning": one axis per topic, so laptops are close to MacBooks and far from toner.
_TOPICS = {"laptop": ("laptop", "macbook"), "toner": ("toner",), "moss": ("moss",)}
calls: list[int] = []


def _fake_embed(texts: list[str]) -> list[list[float]]:
    calls.append(len(texts))
    return [
        cm.normalize([1.0 if any(w in t.lower() for w in words) else 0.01
                      for words in _TOPICS.values()])
        for t in texts
    ]


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    calls.clear()
    cm._cache.clear()
    monkeypatch.setattr(cm.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(cm, "_embed", _fake_embed)


def _article(org, supplier, number, description, price):
    return Article(organization_id=org.id, supplier_id=supplier.id, article_number=number,
                   description=description, unit_price=Decimal(price), currency="USD",
                   unit="piece", quantity=1)


def _db() -> tuple[Session, uuid.UUID]:
    """Acme: the same laptop from an IT and an office supplier, plus toner.
    Another tenant has a cheaper laptop that must never be suggested to Acme."""
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(CommodityGroup(id=IT_HARDWARE, category="Information Technology", name="Hardware"))
    acme, other = Organization(name="Acme", slug="acme", settings={}), Organization(
        name="Other", slug="other", settings={})
    db.add_all([acme, other])
    db.flush()
    it = Supplier(organization_id=acme.id, name="IT Co", category="Information Technology")
    office = Supplier(organization_id=acme.id, name="Office Co", category="Office & Administration")
    foreign = Supplier(organization_id=other.id, name="Other Co", category="Information Technology")
    db.add_all([it, office, foreign])
    db.flush()
    db.add_all([
        _article(acme, it, "IT-1", 'Business laptop 13"', "1650.00"),
        _article(acme, office, "OF-1", 'Business laptop 13"', "1500.00"),
        _article(acme, office, "OF-2", "Printer toner black", "80.00"),
        _article(other, foreign, "X-1", 'Business laptop 13"', "999.00"),
    ])
    db.commit()
    return db, acme.id


def _macbook():
    return [SuggestionLine(description='13" MacBook Air M2', unit_price=Decimal("1409.06"))]


def test_top_matches_keeps_strong_matches_close_to_the_best():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    line = cm.normalize([1.0, 0.0])
    articles = [(a, cm.normalize([0.9, 0.44])), (b, cm.normalize([1.0, 0.1])), (c, [0.0, 1.0])]

    found = cm.top_matches(line, articles)

    # b ≈ 0.99 and a ≈ 0.90 are kept; c = 0 is below the minimum.
    assert [article_id for article_id, _ in found] == [b, a]


def test_top_matches_drops_matches_far_below_the_best():
    a, b = uuid.uuid4(), uuid.uuid4()
    line = cm.normalize([1.0, 0.0])
    # b ≈ 0.99, a = 0.6: a passes the minimum but is more than 0.10 below the best.
    found = cm.top_matches(line, [(a, cm.normalize([0.6, 0.8])), (b, cm.normalize([1.0, 0.1]))])

    assert [article_id for article_id, _ in found] == [b]


def test_cheapest_per_description_keeps_one_offer_per_article():
    offers = [
        SimpleNamespace(description="Laptop", unit_price=Decimal(p)) for p in ("1650", "1500")
    ]

    assert [o.unit_price for o in cm.cheapest_per_description(offers)] == [Decimal("1500")]


def test_price_far_off_the_quote_is_not_plausible():
    assert cm.price_is_plausible(Decimal("1409.06"), Decimal("1438.00"))  # MacBook → laptop
    assert not cm.price_is_plausible(Decimal("15000"), Decimal("62"))  # grinder → CNC service
    assert cm.price_is_plausible(None, Decimal("62"))  # no quoted price: can't judge, keep


def test_implausibly_priced_match_is_hidden():
    db, acme = _db()
    line = [SuggestionLine(description="MacBook", unit_price=Decimal("30000"))]  # 18× the laptop

    assert cm.suggest(line, acme, db, commodity_group_id=IT_HARDWARE) == [[]]


def test_price_difference_is_quoted_minus_negotiated():
    assert cm.price_difference(Decimal("1409.06"), Decimal("1650.00")) == Decimal("-240.94")
    assert cm.price_difference(None, Decimal("1650.00")) is None


def test_only_articles_from_the_request_category_are_suggested():
    db, acme = _db()

    [suggestions] = cm.suggest(_macbook(), acme, db, commodity_group_id=IT_HARDWARE)

    # The office supplier's laptop is cheaper but in another category; other tenants never show.
    assert [s.article_number for s in suggestions] == ["IT-1"]
    assert suggestions[0].price_difference == Decimal("-240.94")


def test_without_a_category_duplicates_collapse_to_the_cheapest_supplier():
    db, acme = _db()

    [suggestions] = cm.suggest(_macbook(), acme, db)

    assert [s.article_number for s in suggestions] == ["OF-1"]  # not IT-1, not toner, not X-1


def test_catalog_is_embedded_once_then_cached():
    db, acme = _db()

    cm.suggest(_macbook(), acme, db)
    cm.suggest(_macbook(), acme, db)

    assert calls == [3, 1, 1]  # Acme's 3 articles once, then one line per request


def test_no_api_key_returns_no_suggestions(monkeypatch):
    db, acme = _db()
    monkeypatch.setattr(cm.settings, "openai_api_key", None)

    assert cm.suggest(_macbook(), acme, db) == [[]]


def test_embedding_failure_returns_no_suggestions(monkeypatch):
    db, acme = _db()

    def broken(_texts):
        raise RuntimeError("network down")

    monkeypatch.setattr(cm, "_embed", broken)

    assert cm.suggest(_macbook(), acme, db) == [[]]
