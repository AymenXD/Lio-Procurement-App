from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import OrganizationMember, User
from app.schemas.extraction import ExtractionRequest, ExtractionResponse
from app.services.extraction import extract_vendor_data

router = APIRouter(prefix="/extraction", tags=["extraction"])


@router.post("", response_model=ExtractionResponse, response_model_by_alias=True)
def extract(
    payload: ExtractionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExtractionResponse:
    """Extract structured vendor data from PDF text via OpenAI.

    Returns ``{success, data?, error?, missingFields?, warnings?, appliedRule?}``: errors are
    part of the payload, not HTTP errors, so the UI can show partial-extraction warnings. The
    user's organisation's booking rules (if any) are applied to the commodity group.
    """
    membership = db.scalar(select(OrganizationMember).where(OrganizationMember.user_id == user.id))
    return extract_vendor_data(payload.text, db, membership.organization_id if membership else None)
