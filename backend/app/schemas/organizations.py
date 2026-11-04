import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

MemberRole = Literal["admin", "buyer", "requester"]

# Request fields an organization may optionally mark as required. (The other
# request fields are always required by the app.)
ConfigurableRequiredField = Literal["vat_id", "department"]


class BookingRule(BaseModel):
    """A tenant's booking rule: lines mentioning a keyword are always booked to one group."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=100)
    keywords: list[str] = Field(min_length=1, max_length=20)
    commodity_group_id: int
    # Applies only if the request total is below this (e.g. "small" subscriptions).
    max_total: float | None = Field(default=None, gt=0)

    @field_validator("keywords")
    @classmethod
    def _clean_keywords(cls, keywords: list[str]) -> list[str]:
        cleaned = [k.strip().lower() for k in keywords if k.strip()]
        if not cleaned:
            raise ValueError("at least one keyword is required")
        return cleaned


class OrganizationSettings(BaseModel):
    """Per-organization configuration. Stored as JSONB, validated here.

    This is the reference pattern for tenant config: keep the storage flexible,
    but validate the shape at the edge so it can't drift into a free-for-all.
    """

    model_config = ConfigDict(extra="forbid")

    required_fields: list[ConfigurableRequiredField] = Field(default_factory=list)
    booking_rules: list[BookingRule] = Field(default_factory=list, max_length=50)


class OrganizationCreate(BaseModel):
    name: str
    slug: str


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


class MyOrganizationOut(OrganizationOut):
    role: MemberRole


class MemberProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None = None
    avatar_url: str | None = None


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: MemberRole
    created_at: datetime
    # Named to match the Supabase join key the frontend already renders.
    profiles: MemberProfileOut | None = None


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    role: str
    invited_by: uuid.UUID
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


class MembersResponse(BaseModel):
    members: list[MemberOut]
    invites: list[InviteOut]


class InviteCreate(BaseModel):
    email: EmailStr
    role: MemberRole = "requester"


class InviteAccept(BaseModel):
    token: str
