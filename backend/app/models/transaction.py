"""
The settled deal, plus its append-only status trail.

Gross and net are stored side by side so a record never implies the farmer
received the headline price.
"""
from dataclasses import dataclass

from app.models import BaseModel

OFFERED = "OFFERED"
ACCEPTED = "ACCEPTED"
LOGISTICS_PENDING = "LOGISTICS_PENDING"
IN_TRANSIT = "IN_TRANSIT"
DELIVERED = "DELIVERED"
PAYMENT_PENDING = "PAYMENT_PENDING"
PAID = "PAID"
COMPLETED = "COMPLETED"
CANCELLED = "CANCELLED"
DISPUTED = "DISPUTED"

STATUSES = (
    OFFERED,
    ACCEPTED,
    LOGISTICS_PENDING,
    IN_TRANSIT,
    DELIVERED,
    PAYMENT_PENDING,
    PAID,
    COMPLETED,
    CANCELLED,
    DISPUTED,
)

#: The happy path from the project documentation, plus the escapes that a real
#: deal needs. Enforced by transaction_service so history can be trusted.
STATUS_FLOW = {
    OFFERED: (ACCEPTED, CANCELLED),
    ACCEPTED: (LOGISTICS_PENDING, CANCELLED, DISPUTED),
    LOGISTICS_PENDING: (IN_TRANSIT, CANCELLED, DISPUTED),
    IN_TRANSIT: (DELIVERED, DISPUTED, CANCELLED),
    DELIVERED: (PAYMENT_PENDING, DISPUTED),
    PAYMENT_PENDING: (PAID, DISPUTED),
    PAID: (COMPLETED, DISPUTED),
    COMPLETED: (),
    CANCELLED: (),
    # A dispute can be closed out either way once the grievance is resolved.
    DISPUTED: (PAYMENT_PENDING, PAID, COMPLETED, CANCELLED),
}

TERMINAL_STATUSES = (COMPLETED, CANCELLED)


@dataclass
class Transaction(BaseModel):
    FLOAT_FIELDS = (
        "quantity",
        "price_per_unit",
        "gross_amount",
        "transport_cost",
        "storage_cost",
        "commission_cost",
        "other_deductions",
        "net_amount",
    )

    id: int = None
    transaction_code: str = None
    offer_id: int = None
    lot_id: int = None
    buyer_id: int = None
    seller_user_id: int = None
    crop_id: int = None
    quantity: float = None
    unit: str = "QUINTAL"
    price_per_unit: float = None
    gross_amount: float = None
    transport_cost: float = 0
    storage_cost: float = 0
    commission_cost: float = 0
    other_deductions: float = 0
    net_amount: float = None
    status: str = ACCEPTED
    expected_delivery_date: str = None
    delivered_at: str = None
    completed_at: str = None
    created_at: str = None
    updated_at: str = None

    def to_dict(self, extra=None):
        data = super().to_dict(extra)
        quantity = float(self.quantity or 0)
        if quantity:
            data["net_price_per_unit"] = round(float(self.net_amount or 0) / quantity, 2)
        else:
            data["net_price_per_unit"] = None
        data["is_terminal"] = self.status in TERMINAL_STATUSES
        return data


@dataclass
class TransactionStatusHistory(BaseModel):
    id: int = None
    transaction_id: int = None
    from_status: str = None
    to_status: str = None
    changed_by_user_id: int = None
    remarks: str = None
    created_at: str = None
