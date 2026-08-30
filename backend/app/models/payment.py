"""
Payment tracking.

No payment gateway is integrated. These rows record what the parties report,
which is enough to make payment reliability visible and to feed trust scoring.
"""
from dataclasses import dataclass

from app.models import BaseModel

PENDING = "PENDING"
PARTIAL = "PARTIAL"
PAID = "PAID"
FAILED = "FAILED"
REFUNDED = "REFUNDED"
STATUSES = (PENDING, PARTIAL, PAID, FAILED, REFUNDED)

MODES = ("UPI", "BANK_TRANSFER", "CASH", "CHEQUE", "OTHER")


@dataclass
class Payment(BaseModel):
    FLOAT_FIELDS = ("amount",)

    id: int = None
    transaction_id: int = None
    amount: float = None
    mode: str = "BANK_TRANSFER"
    reference_no: str = None
    status: str = PENDING
    due_date: str = None
    paid_at: str = None
    recorded_by_user_id: int = None
    remarks: str = None
    created_at: str = None
    updated_at: str = None
