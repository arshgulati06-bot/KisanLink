"""Request shapes for transactions and payments."""
import datetime as dt

from app.models.payment import MODES, STATUSES as PAYMENT_STATUSES
from app.models.transaction import STATUSES
from app.schemas import Field

UPDATE_STATUS_SCHEMA = {
    "status": Field(str, required=True, choices=STATUSES),
    "remarks": Field(str, max_len=500),
}

RECORD_PAYMENT_SCHEMA = {
    "amount": Field(float, required=True, min_value=0.01),
    "mode": Field(str, choices=MODES, default="BANK_TRANSFER"),
    "reference_no": Field(str, max_len=80),
    "status": Field(str, choices=PAYMENT_STATUSES, default="PAID"),
    "paid_at": Field(dt.datetime),
    "due_date": Field(dt.date),
    "remarks": Field(str, max_len=500),
}

TRANSACTION_FILTER_SCHEMA = {
    "status": Field(str, choices=STATUSES),
    "crop_id": Field(int, min_value=1),
    "lot_id": Field(int, min_value=1),
    "scope": Field(str, choices=("buyer", "seller", "all")),
    "order_by": Field(str, max_len=40),
}
