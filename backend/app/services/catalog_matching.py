"""Suggest catalog articles (negotiated prices) for order lines, matched by meaning.

Descriptions are turned into embedding vectors (OpenAI). The org's article vectors are
computed once and kept in memory. Each line is compared only with articles whose supplier
is in the request's commodity category (measured: embeddings alone can't tell "same topic"
from "can replace this item"; the category filter fixes most of that, see docs).
"""

import logging
import math
import time
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models import Article, CommodityGroup
from app.schemas.articles import ArticleSuggestion, SuggestionLine
from app.services.ai import get_client

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
DIMENSIONS = 256  # shorter vectors: the whole catalog fits in a few MB
MAX_SUGGESTIONS = 3
MIN_SIMILARITY = 0.40  # tuned on the Acme quotes; below this a match is too weak
MAX_GAP_FROM_BEST = 0.10  # also drop matches clearly worse than the line's best one
MAX_PRICE_RATIO = 10  # a real replacement costs roughly the same as the quoted item
CENT = Decimal("0.01")

Vector = list[float]

# Per organisation: (number of articles, {article id: vector}). Rebuilt when the count changes.
_cache: dict[uuid.UUID, tuple[int, dict[uuid.UUID, Vector]]] = {}


# --- pure functions ---------------------------------------------------------------------


def normalize(vector: Vector) -> Vector:
    """Scale to length 1, so similarity is a plain dot product."""
    length = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / length for x in vector]


def similarity(a: Vector, b: Vector) -> float:
    """Cosine similarity of two normalized vectors: closer to 1 = closer in meaning."""
    return sum(x * y for x, y in zip(a, b))


def top_matches(
    line: Vector, articles: list[tuple[uuid.UUID, Vector]]
) -> list[tuple[uuid.UUID, float]]:
    """The best articles, best first: above the minimum and close to the best match."""
    scored = sorted(
        ((article_id, similarity(line, vector)) for article_id, vector in articles),
        key=lambda s: s[1],
        reverse=True,
    )
    if not scored:
        return []
    best = scored[0][1]
    good = [s for s in scored if s[1] >= MIN_SIMILARITY and s[1] >= best - MAX_GAP_FROM_BEST]
    return good[:MAX_SUGGESTIONS]


def cheapest_per_description(articles: list[Article]) -> list[Article]:
    """The same article is often sold by several suppliers: keep only the cheapest."""
    best: dict[str, Article] = {}
    for article in articles:
        kept = best.get(article.description)
        if kept is None or article.unit_price < kept.unit_price:
            best[article.description] = article
    return list(best.values())


def price_is_plausible(quoted: Decimal | None, negotiated: Decimal) -> bool:
    """A real replacement costs roughly the same (within 10×). No quoted price: keep it."""
    if not quoted or not negotiated:
        return True
    return max(quoted, negotiated) / min(quoted, negotiated) <= MAX_PRICE_RATIO


def price_difference(quoted: Decimal | None, negotiated: Decimal) -> Decimal | None:
    """Quoted minus negotiated unit price; positive means the catalog is cheaper."""
    if not quoted:
        return None
    return (quoted - negotiated).quantize(CENT)


# --- OpenAI + database ------------------------------------------------------------------


def _embed(texts: list[str]) -> list[Vector]:
    started = time.perf_counter()
    response = get_client().embeddings.create(
        model=EMBEDDING_MODEL, input=texts, dimensions=DIMENSIONS
    )
    logger.info(
        "AI embeddings count=%d duration_ms=%d tokens=%s",
        len(texts),
        (time.perf_counter() - started) * 1000,
        getattr(response.usage, "total_tokens", None),
    )
    return [normalize(item.embedding) for item in response.data]


def _article_vectors(
    organization_id: uuid.UUID, articles: list[Article]
) -> dict[uuid.UUID, Vector]:
    """All of the org's article vectors, embedded once and cached in memory."""
    cached = _cache.get(organization_id)
    if cached and cached[0] == len(articles):
        return cached[1]
    vectors = _embed([a.description for a in articles]) if articles else []
    by_id = {a.id: vector for a, vector in zip(articles, vectors)}
    _cache[organization_id] = (len(articles), by_id)
    return by_id


def suggest(
    lines: list[SuggestionLine],
    organization_id: uuid.UUID,
    db: Session,
    commodity_group_id: int | None = None,
) -> list[list[ArticleSuggestion]]:
    """Up to 3 catalog articles per line. Never raises: suggestions are optional."""
    empty: list[list[ArticleSuggestion]] = [[] for _ in lines]
    wanted = [i for i, line in enumerate(lines) if line.description.strip()]
    if not settings.openai_api_key or not wanted:
        return empty

    articles = list(
        db.scalars(
            select(Article)
            .where(Article.organization_id == organization_id)
            .options(joinedload(Article.supplier))
        )
    )
    group = db.get(CommodityGroup, commodity_group_id) if commodity_group_id else None
    in_category = [
        a for a in articles
        if group is None or (a.supplier is not None and a.supplier.category == group.category)
    ]
    candidates = cheapest_per_description(in_category)

    try:
        vectors = _article_vectors(organization_id, articles)
        line_vectors = _embed([lines[i].description for i in wanted])
    except Exception as exc:  # noqa: BLE001 — a failure must not break the request form
        logger.warning("Catalog suggestions failed: %s", type(exc).__name__)
        return empty

    pool = [(a.id, vectors[a.id]) for a in candidates if a.id in vectors]
    by_id = {a.id: a for a in candidates}
    result = empty
    for i, vector in zip(wanted, line_vectors):
        quoted = lines[i].unit_price
        # Rank by meaning, then drop articles whose price is far off the quoted one.
        result[i] = [
            _to_suggestion(by_id[article_id], score, quoted)
            for article_id, score in top_matches(vector, pool)
            if price_is_plausible(quoted, Decimal(str(by_id[article_id].unit_price)))
        ]
    return result


def _to_suggestion(article: Article, score: float, quoted: Decimal | None) -> ArticleSuggestion:
    return ArticleSuggestion(
        article_id=article.id,
        article_number=article.article_number,
        description=article.description,
        supplier_name=article.supplier.name if article.supplier else None,
        unit_price=article.unit_price,
        currency=article.currency,
        unit=article.unit,
        similarity=round(score, 3),
        price_difference=price_difference(quoted, Decimal(str(article.unit_price))),
    )
