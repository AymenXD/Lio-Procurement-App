from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _drop_nulls(data: object) -> object:
    """Sometimes, the AI returns null which result in total Crash.

    Dropping them lets the field default apply, so a missing value is reported as a
    missing field instead of failing the whole extraction.
    """
    if isinstance(data, dict):
        return {key: value for key, value in data.items() if value is not None}
    return data


class PdfParseResponse(BaseModel):
    text: str


class ExtractionRequest(BaseModel):
    text: str


# camelCase on the wire — matches the AI's JSON output format and what the
# frontend's extraction flow already consumes.
class OrderLineData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    position_description: str = Field(default="", alias="positionDescription")
    unit_price: float = Field(default=0, alias="unitPrice")
    amount: float = 0
    unit: str = ""
    total_price: float = Field(default=0, alias="totalPrice")

    _nulls_to_defaults = model_validator(mode="before")(_drop_nulls)


class SkippedLineData(OrderLineData):
    """A priced row the AI labelled as not part of the order (e.g. an alternative)."""

    kind: str


class ExtractedVendorData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = ""
    vendor_name: str = Field(default="", alias="vendorName")
    # The quote's recipient; asked for so the AI can't confuse it with the vendor.
    customer_name: str = Field(default="", alias="customerName")
    vat_id: str = Field(default="", alias="vatId")
    department: str = ""
    order_lines: list[OrderLineData] = Field(default_factory=list, alias="orderLines")
    tax_amount: float = Field(default=0, alias="taxAmount")
    total_cost: float = Field(default=0, alias="totalCost")
    commodity_group_id: int | None = Field(default=None, alias="commodityGroupId")
    commodity_group_name: str | None = Field(default=None, alias="commodityGroupName")

    _nulls_to_defaults = model_validator(mode="before")(_drop_nulls)


# The AI labels every row of the price table; our code decides which kinds count.
RowKind = Literal[
    "item", "shipping", "fee", "alternative", "optional", "subtotal", "heading", "tax"
]


# What the AI must return, enforced by OpenAI Structured Outputs: every key present,
# null allowed, numbers must be numbers. Converted into ExtractedVendorData afterwards.
class QuoteLine(BaseModel):
    kind: RowKind
    position_description: str | None = Field(alias="positionDescription")
    unit_price: float | None = Field(alias="unitPrice")
    amount: float | None
    unit: str | None
    total_price: float | None = Field(alias="totalPrice")


class QuoteExtraction(BaseModel):
    title: str | None
    vendor_name: str | None = Field(alias="vendorName")
    customer_name: str | None = Field(alias="customerName")
    vat_id: str | None = Field(alias="vatId")
    department: str | None
    order_lines: list[QuoteLine] = Field(alias="orderLines")
    tax_amount: float | None = Field(alias="taxAmount")
    total_cost: float | None = Field(alias="totalCost")
    # Step 1 of classification: one of the ~22 categories. The group is picked in a
    # second, small call among that category's groups (services/classification.py).
    commodity_category: str | None = Field(alias="commodityCategory")


class GroupChoice(BaseModel):
    """Step 2 of classification: one group id from the chosen category's list."""

    commodity_group_id: int | None = Field(alias="commodityGroupId")


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    success: bool
    data: ExtractedVendorData | None = None
    error: str | None = None
    missing_fields: list[str] | None = Field(default=None, alias="missingFields")
    # Numbers that don't add up (see services/reconciliation.py); shown to the user.
    warnings: list[str] | None = None
    # Label of the org booking rule that set the commodity group, if any.
    applied_rule: str | None = Field(default=None, alias="appliedRule")
    # Priced rows left out of the order, shown so the user can add one back.
    skipped_lines: list[SkippedLineData] | None = Field(default=None, alias="skippedLines")
