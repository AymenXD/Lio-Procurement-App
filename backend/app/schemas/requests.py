import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RequestStatus = Literal["open", "in_progress", "closed"]
ApprovalStatus = Literal["pending", "approved", "rejected"]


# ---------------------------------------------------------------------------
# Inputs (camelCase — matches what the frontend forms already send)
# ---------------------------------------------------------------------------

class OrderLineIn(BaseModel):
    position_description: str = Field(alias="positionDescription")
    # Not negative: a fake "discount" line could otherwise push a request under the limit.
    unit_price: float = Field(alias="unitPrice", ge=0)
    amount: float = Field(ge=0)
    unit: str
    # Ignored: the server computes amount × unit price.
    total_price: float | None = Field(default=None, alias="totalPrice")
    # A catalog line: the server takes its price and unit from the catalog, not from here.
    article_id: uuid.UUID | None = Field(default=None, alias="articleId")
    quoted_unit_price: float | None = Field(default=None, alias="quotedUnitPrice")


class RequestCreate(BaseModel):
    requestor_name: str = Field(alias="requestorName")
    title: str = Field(alias="titleShortDescription")
    vendor_name: str = Field(alias="vendorName")
    vat_id: str | None = Field(default=None, alias="vatId")
    commodity_group_id: int = Field(alias="commodityGroupId")
    # Ignored: the server computes sum of lines + tax.
    total_cost: float | None = Field(default=None, alias="totalCost")
    tax_amount: float | None = Field(default=None, alias="taxAmount", ge=0)
    department: str | None = None
    order_lines: list[OrderLineIn] = Field(alias="orderLines", min_length=1)


class RequestUpdate(BaseModel):
    requestor_name: str = Field(alias="requestorName")
    title: str
    vendor_name: str = Field(alias="vendorName")
    vat_id: str | None = Field(default=None, alias="vatId")
    commodity_group_id: int = Field(alias="commodityGroupId")
    # Ignored: the server computes sum of lines + tax.
    total_cost: float | None = Field(default=None, alias="totalCost")
    tax_amount: float | None = Field(default=None, alias="taxAmount", ge=0)
    department: str | None = None
    order_lines: list[OrderLineIn] = Field(alias="orderLines")


class StatusUpdate(BaseModel):
    status: RequestStatus


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]


# ---------------------------------------------------------------------------
# Outputs (snake_case — matches the DB row shapes the frontend renders)
# ---------------------------------------------------------------------------

class CommodityGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    name: str


class OrderLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: uuid.UUID
    position_description: str
    unit_price: float
    amount: float
    unit: str
    total_price: float
    line_order: int
    article_id: uuid.UUID | None = None
    quoted_unit_price: float | None = None
    created_at: datetime


class RequestActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    summary: str
    detail: dict | None
    created_at: datetime


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID | None
    created_by: uuid.UUID | None
    requestor_name: str
    title: str
    vendor_name: str
    vat_id: str | None
    commodity_group_id: int | None
    department: str | None
    status: RequestStatus
    approval_status: ApprovalStatus
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    total_cost: float | None
    tax_amount: float | None = None
    approval_source: Literal["auto", "manual"] | None = None
    created_at: datetime
    updated_at: datetime
    order_lines: list[OrderLineOut]
    # Serialized as ``commodity_groups`` (the join key the frontend renders) but
    # read from the ORM's ``commodity_group`` relationship.
    commodity_groups: CommodityGroupOut | None = Field(
        default=None, validation_alias="commodity_group"
    )


# --- Booking rule preview (POST /requests/booking-rule-preview) -----------------------------


class BookingPreviewLine(BaseModel):
    description: str
    total_price: float = 0


class BookingPreviewRequest(BaseModel):
    lines: list[BookingPreviewLine] = Field(max_length=200)


class AppliedBookingRule(BaseModel):
    id: str
    label: str
    commodity_group_id: int
    commodity_group_name: str


class BookingPreviewResponse(BaseModel):
    rule: AppliedBookingRule | None
