"""A dispute or complaint raised against a transaction or a counterparty."""
from dataclasses import dataclass

from app.models import BaseModel

PAYMENT_DELAY = "PAYMENT_DELAY"
QUALITY_DISPUTE = "QUALITY_DISPUTE"
QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
DELIVERY_ISSUE = "DELIVERY_ISSUE"
PRICE_DISPUTE = "PRICE_DISPUTE"
OTHER = "OTHER"
CATEGORIES = (
    PAYMENT_DELAY,
    QUALITY_DISPUTE,
    QUANTITY_MISMATCH,
    DELIVERY_ISSUE,
    PRICE_DISPUTE,
    OTHER,
)

OPEN = "OPEN"
UNDER_REVIEW = "UNDER_REVIEW"
RESOLVED = "RESOLVED"
REJECTED = "REJECTED"
WITHDRAWN = "WITHDRAWN"
STATUSES = (OPEN, UNDER_REVIEW, RESOLVED, REJECTED, WITHDRAWN)

STATUS_FLOW = {
    OPEN: (UNDER_REVIEW, RESOLVED, REJECTED, WITHDRAWN),
    UNDER_REVIEW: (RESOLVED, REJECTED),
    RESOLVED: (),
    REJECTED: (),
    WITHDRAWN: (),
}

CLOSED_STATUSES = (RESOLVED, REJECTED, WITHDRAWN)


@dataclass
class Grievance(BaseModel):
    id: int = None
    ticket_no: str = None
    transaction_id: int = None
    raised_by_user_id: int = None
    against_user_id: int = None
    category: str = OTHER
    subject: str = None
    description: str = None
    status: str = OPEN
    resolution: str = None
    handled_by_user_id: int = None
    resolved_at: str = None
    created_at: str = None
    updated_at: str = None
