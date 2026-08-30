"""
A quantity of a crop a farmer or FPO wants to sell.

This is the unit the whole platform revolves around: intelligence is computed
for a lot, buyers make offers on a lot, and a transaction settles a lot.
"""
from dataclasses import dataclass

from app.models import BaseModel

DRAFT = "DRAFT"
LISTED = "LISTED"
OFFER_RECEIVED = "OFFER_RECEIVED"
RESERVED = "RESERVED"
SOLD = "SOLD"
EXPIRED = "EXPIRED"
CANCELLED = "CANCELLED"

STATUSES = (DRAFT, LISTED, OFFER_RECEIVED, RESERVED, SOLD, EXPIRED, CANCELLED)
#: Statuses in which a buyer may still make an offer.
OPEN_STATUSES = (LISTED, OFFER_RECEIVED)

GRADES = ("A", "B", "C")


@dataclass
class Lot(BaseModel):
    BOOL_FIELDS = ("is_aggregated",)
    FLOAT_FIELDS = (
        "quantity",
        "moisture_percent",
        "expected_price",
        "latitude",
        "longitude",
    )

    id: int = None
    lot_code: str = None
    seller_user_id: int = None
    seller_type: str = "FARMER"
    fpo_id: int = None
    crop_id: int = None
    variety: str = None
    quantity: float = None
    unit: str = "QUINTAL"
    grade: str = "B"
    moisture_percent: float = None
    expected_price: float = None
    harvest_date: str = None
    available_from: str = None
    available_until: str = None
    village: str = None
    district: str = None
    state: str = "Maharashtra"
    latitude: float = None
    longitude: float = None
    status: str = DRAFT
    is_aggregated: int = 0
    notes: str = None
    created_at: str = None
    updated_at: str = None

    @property
    def is_open(self):
        return self.status in OPEN_STATUSES

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None
