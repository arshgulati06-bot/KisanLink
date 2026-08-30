"""
A concrete, digital price offer on a specific lot.

Offers can go in both directions: a buyer offers, and the farmer can counter.
That two-way flow is what gives the farmer bargaining room instead of a
take-it-or-leave-it price.
"""
from dataclasses import dataclass

from app.models import BaseModel

PENDING = "PENDING"
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
WITHDRAWN = "WITHDRAWN"
COUNTERED = "COUNTERED"
EXPIRED = "EXPIRED"
STATUSES = (PENDING, ACCEPTED, REJECTED, WITHDRAWN, COUNTERED, EXPIRED)
#: Statuses from which the offer can still change.
LIVE_STATUSES = (PENDING, COUNTERED)

BUYER = "BUYER"
FARMER = "FARMER"


@dataclass
class Offer(BaseModel):
    FLOAT_FIELDS = ("price_per_unit", "quantity")

    id: int = None
    lot_id: int = None
    requirement_id: int = None
    buyer_id: int = None
    seller_user_id: int = None
    price_per_unit: float = None
    quantity: float = None
    unit: str = "QUINTAL"
    delivery_mode: str = "DELIVERED_AT_BUYER"
    transport_borne_by: str = FARMER
    payment_terms_days: int = 7
    valid_until: str = None
    status: str = PENDING
    initiated_by: str = BUYER
    parent_offer_id: int = None
    message: str = None
    responded_at: str = None
    created_at: str = None
    updated_at: str = None

    @property
    def gross_amount(self):
        return float(self.price_per_unit or 0) * float(self.quantity or 0)

    def to_dict(self, extra=None):
        data = super().to_dict(extra)
        data["gross_amount"] = round(self.gross_amount, 2)
        return data
