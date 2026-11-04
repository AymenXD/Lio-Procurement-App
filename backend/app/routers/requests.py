import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_membership, require_buyer_or_admin
from app.db.session import get_db
from app.models import (
    Article,
    CommodityGroup,
    OrderLine,
    Organization,
    OrganizationMember,
    ProcurementRequest,
    RequestActivity,
    RequestDocument,
)
from app.schemas.requests import (
    AppliedBookingRule,
    ApprovalDecision,
    BookingPreviewRequest,
    BookingPreviewResponse,
    OrderLineIn,
    RequestActivityOut,
    RequestCreate,
    RequestOut,
    RequestUpdate,
    StatusUpdate,
)
from app.services.booking_rules import match_rule, rules_for

router = APIRouter(prefix="/requests", tags=["requests"])

MAX_PDF_BYTES = 10 * 1024 * 1024

# Human-readable labels for the fields we track in the activity log.
_FIELD_LABELS = {
    "requestor_name": "requestor",
    "title": "title",
    "vendor_name": "vendor",
    "vat_id": "tax ID",
    "commodity_group_id": "commodity group",
    "total_cost": "total cost",
    "department": "department",
    "order_lines": "order lines",
}


def _load_request_options():
    return (
        selectinload(ProcurementRequest.order_lines),
        selectinload(ProcurementRequest.commodity_group),
    )


def _get_org_request(
    db: Session, request_id: uuid.UUID, organization_id: uuid.UUID
) -> ProcurementRequest:
    request = db.scalar(
        select(ProcurementRequest)
        .options(*_load_request_options())
        # Refresh already-loaded relationships (e.g. after an update commit).
        .execution_options(populate_existing=True)
        .where(
            ProcurementRequest.id == request_id,
            ProcurementRequest.organization_id == organization_id,
        )
    )
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found or you do not have permission to access it",
        )
    return request


def _validate_commodity_group(db: Session, commodity_group_id: int) -> None:
    if db.get(CommodityGroup, commodity_group_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown commodity group id: {commodity_group_id}",
        )


def _enforce_required_fields(
    db: Session, organization_id: uuid.UUID, payload: RequestCreate | RequestUpdate
) -> None:
    """Enforce the org's configurable required fields (see OrganizationSettings)."""
    org = db.get(Organization, organization_id)
    required = (org.settings or {}).get("required_fields", []) if org else []
    missing = [field for field in required if not getattr(payload, field, None)]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing fields required by your organization: {', '.join(missing)}",
        )


def _log_activity(
    db: Session,
    request_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    summary: str,
    detail: dict | None = None,
) -> None:
    db.add(
        RequestActivity(
            request_id=request_id,
            actor_id=actor_id,
            action=action,
            summary=summary,
            detail=detail,
        )
    )


def _build_order_lines(
    lines: list[OrderLineIn], organization_id: uuid.UUID, db: Session
) -> tuple[list[OrderLine], list[tuple[str, dict]]]:
    """Order lines from the payload, plus an activity note per catalog line.

    A catalog line (``article_id`` set) gets its unit price and unit from the catalog, never
    from the browser, so a "negotiated price" can't be faked. The article must belong to the
    caller's organisation; otherwise 404.
    """
    built: list[OrderLine] = []
    notes: list[tuple[str, dict]] = []
    for index, line in enumerate(lines, start=1):
        unit_price, unit, total_price = line.unit_price, line.unit, line.total_price
        if line.article_id is not None:
            article = db.scalar(
                select(Article).where(
                    Article.id == line.article_id, Article.organization_id == organization_id
                )
            )
            if article is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Catalog article not found"
                )
            negotiated = Decimal(str(article.unit_price))
            unit_price, unit = negotiated, article.unit
            total_price = (negotiated * Decimal(str(line.amount))).quantize(Decimal("0.01"))
            quoted = (
                f" (quoted ${line.quoted_unit_price:,.2f})" if line.quoted_unit_price else ""
            )
            notes.append((
                f"Line {index} uses catalog article {article.article_number} "
                f"at the negotiated ${negotiated:,.2f} / {unit}{quoted}",
                {
                    "line": index,
                    "article_id": str(article.id),
                    "negotiated_unit_price": str(negotiated),
                    "quoted_unit_price": line.quoted_unit_price,
                },
            ))
        built.append(
            OrderLine(
                position_description=line.position_description,
                unit_price=unit_price,
                amount=line.amount,
                unit=unit,
                total_price=total_price,
                line_order=index,
                article_id=line.article_id,
                quoted_unit_price=line.quoted_unit_price if line.article_id else None,
            )
        )
    return built, notes


def _apply_booking_rule(
    db: Session, organization_id: uuid.UUID, lines: list[OrderLine], chosen_group_id: int
) -> tuple[int, tuple[str, dict] | None]:
    """The group to store: a matching org booking rule always beats the AI's or user's choice.

    Returns the group id and, if a rule applied, an activity note. Line totals come from the
    stored lines, not from the browser's request total.
    """
    rule = match_rule(
        [(line.position_description, Decimal(str(line.total_price))) for line in lines],
        rules_for(db, organization_id),
    )
    group = db.get(CommodityGroup, rule.commodity_group_id) if rule else None
    if rule is None or group is None:
        return chosen_group_id, None
    was = db.get(CommodityGroup, chosen_group_id)
    summary = f"Booked to {group.name} by the rule '{rule.label}'"
    if was is not None and was.id != group.id:
        summary += f" (was {was.name})"
    return group.id, (summary, {"rule_id": rule.id, "was_commodity_group_id": chosen_group_id})


def _order_lines_signature(lines) -> list[tuple]:
    return [
        (
            line.position_description,
            float(line.unit_price),
            float(line.amount),
            line.unit,
            float(line.total_price),
        )
        for line in lines
    ]


def _changed_fields(
    request: ProcurementRequest, payload: RequestUpdate, new_lines: list[OrderLine]
) -> list[str]:
    """Return the field keys whose value differs between the request and payload."""
    changed: list[str] = []
    if request.requestor_name != payload.requestor_name:
        changed.append("requestor_name")
    if request.title != payload.title:
        changed.append("title")
    if request.vendor_name != payload.vendor_name:
        changed.append("vendor_name")
    if (request.vat_id or "") != (payload.vat_id or ""):
        changed.append("vat_id")
    if request.commodity_group_id != payload.commodity_group_id:
        changed.append("commodity_group_id")
    if float(request.total_cost or 0) != float(payload.total_cost or 0):
        changed.append("total_cost")
    if (request.department or "") != (payload.department or ""):
        changed.append("department")
    old_lines = _order_lines_signature(
        sorted(request.order_lines, key=lambda line: line.line_order)
    )
    # Compare with the lines as they will be stored (catalog prices already applied).
    if old_lines != _order_lines_signature(new_lines):
        changed.append("order_lines")
    return changed


@router.get("", response_model=list[RequestOut])
def list_requests(
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> list[RequestOut]:
    requests = db.scalars(
        select(ProcurementRequest)
        .options(*_load_request_options())
        .where(ProcurementRequest.organization_id == membership.organization_id)
        .order_by(ProcurementRequest.created_at.desc())
    )
    return [RequestOut.model_validate(r) for r in requests]


@router.get("/{request_id}", response_model=RequestOut)
def get_request(
    request_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> RequestOut:
    return RequestOut.model_validate(
        _get_org_request(db, request_id, membership.organization_id)
    )


@router.post("/booking-rule-preview", response_model=BookingPreviewResponse)
def preview_booking_rule(
    payload: BookingPreviewRequest,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> BookingPreviewResponse:
    """Which org booking rule would apply to these lines (the form locks the group)."""
    rule = match_rule(
        [(line.description, Decimal(str(line.total_price))) for line in payload.lines],
        rules_for(db, membership.organization_id),
    )
    group = db.get(CommodityGroup, rule.commodity_group_id) if rule else None
    if rule is None or group is None:
        return BookingPreviewResponse(rule=None)
    return BookingPreviewResponse(rule=AppliedBookingRule(
        id=rule.id, label=rule.label, commodity_group_id=group.id, commodity_group_name=group.name
    ))


@router.post("", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: RequestCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> RequestOut:
    _validate_commodity_group(db, payload.commodity_group_id)
    _enforce_required_fields(db, membership.organization_id, payload)

    # Vendor fields are already cleaned up during extraction, so we can persist
    # them directly here.
    request = ProcurementRequest(
        user_id=membership.user_id,
        requestor_name=payload.requestor_name,
        title=payload.title,
        vendor_name=payload.vendor_name,
        vat_id=payload.vat_id,
        commodity_group_id=payload.commodity_group_id,
        total_cost=payload.total_cost,
        department=payload.department,
        organization_id=membership.organization_id,
        created_by=membership.user_id,
        status="open",
    )
    request.order_lines, catalog_notes = _build_order_lines(
        payload.order_lines, membership.organization_id, db
    )
    request.commodity_group_id, booking_note = _apply_booking_rule(
        db, membership.organization_id, request.order_lines, payload.commodity_group_id
    )
    db.add(request)
    db.flush()
    _log_activity(db, request.id, membership.user_id, "created", "Request created")
    if booking_note:
        _log_activity(db, request.id, membership.user_id, "booking_rule", *booking_note)
    for summary, detail in catalog_notes:
        _log_activity(db, request.id, membership.user_id, "catalog_article", summary, detail)
    db.commit()

    request = _get_org_request(db, request.id, membership.organization_id)
    return RequestOut.model_validate(request)


@router.put("/{request_id}", response_model=RequestOut)
def update_request(
    request_id: uuid.UUID,
    payload: RequestUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> RequestOut:
    request = _get_org_request(db, request_id, membership.organization_id)
    _validate_commodity_group(db, payload.commodity_group_id)
    _enforce_required_fields(db, membership.organization_id, payload)

    new_lines, catalog_notes = _build_order_lines(
        payload.order_lines, membership.organization_id, db
    )
    group_id, booking_note = _apply_booking_rule(
        db, membership.organization_id, new_lines, payload.commodity_group_id
    )
    overridden = group_id != payload.commodity_group_id
    payload = payload.model_copy(update={"commodity_group_id": group_id})
    changed = _changed_fields(request, payload, new_lines)
    already_linked = {line.article_id for line in request.order_lines if line.article_id}

    request.requestor_name = payload.requestor_name
    request.title = payload.title
    request.vendor_name = payload.vendor_name
    request.vat_id = payload.vat_id
    request.commodity_group_id = payload.commodity_group_id
    request.total_cost = payload.total_cost
    request.department = payload.department

    # Replace order lines (same semantics as the original delete-and-insert).
    request.order_lines = new_lines

    # Log a rule only when it overrode the group chosen in this edit.
    if booking_note and overridden:
        _log_activity(db, request.id, membership.user_id, "booking_rule", *booking_note)

    # Log only articles newly linked by this edit.
    for summary, detail in catalog_notes:
        if uuid.UUID(detail["article_id"]) not in already_linked:
            _log_activity(db, request.id, membership.user_id, "catalog_article", summary, detail)

    if changed:
        labels = [_FIELD_LABELS.get(f, f) for f in changed]
        _log_activity(
            db,
            request.id,
            membership.user_id,
            "updated",
            f"Updated {', '.join(labels)}",
            {"changed_fields": changed},
        )
    db.commit()

    request = _get_org_request(db, request_id, membership.organization_id)
    return RequestOut.model_validate(request)


@router.patch("/{request_id}/status", response_model=RequestOut)
def update_status(
    request_id: uuid.UUID,
    payload: StatusUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> RequestOut:
    request = _get_org_request(db, request_id, membership.organization_id)

    if request.status != payload.status:
        _log_activity(
            db,
            request.id,
            membership.user_id,
            "status_changed",
            f"Status changed from {request.status} to {payload.status}",
            {"from": request.status, "to": payload.status},
        )
        request.status = payload.status
        db.commit()

    request = _get_org_request(db, request_id, membership.organization_id)
    return RequestOut.model_validate(request)


@router.patch("/{request_id}/approval", response_model=RequestOut)
def decide_approval(
    request_id: uuid.UUID,
    payload: ApprovalDecision,
    membership: OrganizationMember = Depends(require_buyer_or_admin),
    db: Session = Depends(get_db),
) -> RequestOut:
    """Approve or reject a pending request (buyers and admins only)."""
    request = _get_org_request(db, request_id, membership.organization_id)

    if request.approval_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request has already been {request.approval_status}.",
        )

    request.approval_status = payload.decision
    request.approved_by = membership.user_id
    request.approved_at = datetime.now(timezone.utc)
    _log_activity(
        db,
        request.id,
        membership.user_id,
        payload.decision,
        f"Request {payload.decision}",
    )
    db.commit()

    request = _get_org_request(db, request_id, membership.organization_id)
    return RequestOut.model_validate(request)


@router.get("/{request_id}/activity", response_model=list[RequestActivityOut])
def get_activity(
    request_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> list[RequestActivityOut]:
    _get_org_request(db, request_id, membership.organization_id)  # scope check
    activity = db.scalars(
        select(RequestActivity)
        .where(RequestActivity.request_id == request_id)
        .order_by(RequestActivity.created_at.desc())
    )
    return [RequestActivityOut.model_validate(a) for a in activity]


@router.put("/{request_id}/document", status_code=status.HTTP_204_NO_CONTENT)
async def upload_document(
    request_id: uuid.UUID,
    file: UploadFile,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> None:
    """Attach (or replace) the original PDF for a request."""
    request = _get_org_request(db, request_id, membership.organization_id)

    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Please upload a PDF file"
        )
    content = await file.read()
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="PDF exceeds the 10MB limit",
        )

    document = db.scalar(
        select(RequestDocument).where(RequestDocument.request_id == request.id)
    )
    if document is None:
        document = RequestDocument(request_id=request.id)
        db.add(document)
    document.filename = file.filename or "document.pdf"
    document.content_type = "application/pdf"
    document.content = content

    _log_activity(
        db,
        request.id,
        membership.user_id,
        "document_attached",
        f"Attached document {document.filename}",
    )
    db.commit()


@router.get("/{request_id}/document")
def get_document(
    request_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> Response:
    _get_org_request(db, request_id, membership.organization_id)  # scope check
    document = db.scalar(
        select(RequestDocument).where(RequestDocument.request_id == request_id)
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No document attached"
        )
    return Response(
        content=document.content,
        media_type=document.content_type,
        headers={"Content-Disposition": f'inline; filename="{document.filename}"'},
    )


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_request(
    request_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> None:
    request = _get_org_request(db, request_id, membership.organization_id)
    db.delete(request)  # order lines, activity, document cascade
    db.commit()
