import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    article_number: str
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    description: str
    unit_price: Decimal
    currency: str
    unit: str
    quantity: Decimal
    created_at: datetime


class ArticlePage(BaseModel):
    """A page of articles plus the totals the UI needs to render pagination."""

    items: list[ArticleOut]
    total: int
    limit: int
    offset: int


# --- Catalog suggestions (POST /articles/suggestions) ---------------------------------------


class SuggestionLine(BaseModel):
    description: str
    unit_price: Decimal | None = None  # the quoted price, to compute the difference


class SuggestionRequest(BaseModel):
    lines: list[SuggestionLine] = Field(max_length=50)
    # Only articles from suppliers in this group's category are suggested (all if omitted).
    commodity_group_id: int | None = None


class ArticleSuggestion(BaseModel):
    article_id: uuid.UUID
    article_number: str
    description: str
    supplier_name: str | None
    unit_price: Decimal  # the negotiated price
    currency: str
    unit: str
    similarity: float  # 0..1, how close in meaning to the order line
    price_difference: Decimal | None  # quoted minus negotiated; positive = catalog is cheaper


class SuggestionResponse(BaseModel):
    # One list per request line, in the same order; empty when nothing is similar enough.
    lines: list[list[ArticleSuggestion]]
