"""Request shapes for offers."""
import datetime as dt

from app.models.buyer_requirement import DELIVERY_MODES
from app.models.crop import UNITS
from app.models.offer import STATUSES
from app.schemas import Field

CREATE_OFFER_SCHEMA = {
    "lot_id": Field(int, required=True, min_value=1),
    "requirement_id": Field(int, min_value=1),
    "price_per_unit": Field(float, required=True, min_value=0.01),
    "quantity": Field(float, min_value=0.01),
    "unit": Field(str, choices=UNITS),
    "delivery_mode": Field(str, choices=DELIVERY_MODES, default="DELIVERED_AT_BUYER"),
    "transport_borne_by": Field(str, choices=("BUYER", "FARMER"), default="FARMER"),
    "payment_terms_days": Field(int, default=7, min_value=0, max_value=180),
    "valid_until": Field(dt.date),
    "message": Field(str, max_len=500),
}

COUNTER_OFFER_SCHEMA = {
    "price_per_unit": Field(float, required=True, min_value=0.01),
    "quantity": Field(float, min_value=0.01),
    "unit": Field(str, choices=UNITS),
    "delivery_mode": Field(str, choices=DELIVERY_MODES),
    "transport_borne_by": Field(str, choices=("BUYER", "FARMER")),
    "payment_terms_days": Field(int, min_value=0, max_value=180),
    "valid_until": Field(dt.date),
    "message": Field(str, max_len=500),
}

RESPOND_SCHEMA = {"reason": Field(str, max_len=500)}

OFFER_FILTER_SCHEMA = {
    "lot_id": Field(int, min_value=1),
    "status": Field(str, choices=STATUSES),
    "crop_id": Field(int, min_value=1),
    "scope": Field(str, choices=("buyer", "seller", "all")),
    "order_by": Field(str, max_len=40),
}
