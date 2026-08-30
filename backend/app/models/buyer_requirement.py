"""
A buyer's standing demand: what they want, how much, at what quality and price.

This is the demand-side input to matching. Without it, "buyer demand" in the
problem statement cannot be demonstrated.
"""
from dataclasses import dataclass

from app.models import BaseModel

OPEN = "OPEN"
PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
FULFILLED = "FULFILLED"
CLOSED = "CLOSED"
EXPIRED = "EXPIRED"
STATUSES = (OPEN, PARTIALLY_FULFILLED, FULFILLED, CLOSED, EXPIRED)
#: Statuses in which the requirement still takes part in matching.
ACTIVE_STATUSES = (OPEN, PARTIALLY_FULFILLED)

FARM_GATE = "FARM_GATE"
BUYER_PICKUP = "BUYER_PICKUP"
DELIVERED_AT_BUYER = "DELIVERED_AT_BUYER"
DELIVERY_MODES = (FARM_GATE, BUYER_PICKUP, DELIVERED_AT_BUYER)

#: Delivery modes where the buyer, not the farmer, pays to move the crop.
BUYER_PAYS_TRANSPORT = (FARM_GATE, BUYER_PICKUP)


@dataclass
class BuyerRequirement(BaseModel):
    FLOAT_FIELDS = (
        "required_quantity",
        "fulfilled_quantity",
        "max_moisture_percent",
        "price_min",
        "price_max",
        "latitude",
        "longitude",
    )

    id: int = None
    buyer_id: int = None
    crop_id: int = None
    variety: str = None
    required_quantity: float = None
    fulfilled_quantity: float = 0
    unit: str = "QUINTAL"
    min_grade: str = "C"
    max_moisture_percent: float = None
    quality_notes: str = None
    price_min: float = None
    price_max: float = None
    delivery_mode: str = DELIVERED_AT_BUYER
    delivery_district: str = None
    delivery_state: str = "Maharashtra"
    latitude: float = None
    longitude: float = None
    payment_terms_days: int = 7
    valid_from: str = None
    valid_until: str = None
    status: str = OPEN
    notes: str = None
    created_at: str = None
    updated_at: str = None

    @property
    def remaining_quantity(self):
        return max(0.0, float(self.required_quantity or 0) - float(self.fulfilled_quantity or 0))

    @property
    def indicative_price(self):
        """
        The single price used when comparing this demand against others.

        We take the midpoint of the declared band, so a buyer cannot win the
        ranking just by quoting a wide range with a high ceiling.
        """
        low, high = self.price_min, self.price_max
        if low is not None and high is not None:
            return (float(low) + float(high)) / 2.0
        if high is not None:
            return float(high)
        if low is not None:
            return float(low)
        return None

    def to_dict(self, extra=None):
        data = super().to_dict(extra)
        data["remaining_quantity"] = self.remaining_quantity
        data["indicative_price"] = self.indicative_price
        return data
