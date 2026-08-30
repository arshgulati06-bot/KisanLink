"""Request shapes for buyer profiles and buyer demand."""
import datetime as dt

from app.models.buyer_profile import BUYER_TYPES
from app.models.buyer_requirement import DELIVERY_MODES, STATUSES
from app.models.crop import UNITS
from app.models.lot import GRADES
from app.schemas import Field, GST_PATTERN

BUYER_PROFILE_SCHEMA = {
    "business_name": Field(str, min_len=2, max_len=180),
    "buyer_type": Field(str, choices=BUYER_TYPES),
    "gst_number": Field(str, pattern=GST_PATTERN, max_len=20),
    "license_number": Field(str, max_len=60),
    "address": Field(str, max_len=255),
    "district": Field(str, max_len=120),
    "state": Field(str, max_len=120),
    "latitude": Field(float, min_value=-90, max_value=90),
    "longitude": Field(float, min_value=-180, max_value=180),
}

BUYER_FILTER_SCHEMA = {
    "buyer_type": Field(str, choices=BUYER_TYPES),
    "verification_status": Field(str, max_len=30),
    "district": Field(str, max_len=120),
    "q": Field(str, max_len=180),
    "order_by": Field(str, max_len=40),
}

CREATE_REQUIREMENT_SCHEMA = {
    "crop_id": Field(int, required=True, min_value=1),
    "variety": Field(str, max_len=120),
    "required_quantity": Field(float, required=True, min_value=0.01),
    "unit": Field(str, choices=UNITS),
    "min_grade": Field(str, choices=GRADES, default="C"),
    "max_moisture_percent": Field(float, min_value=0, max_value=100),
    "quality_notes": Field(str, max_len=500),
    "price_min": Field(float, min_value=0),
    "price_max": Field(float, min_value=0),
    "delivery_mode": Field(str, choices=DELIVERY_MODES, default="DELIVERED_AT_BUYER"),
    "delivery_district": Field(str, max_len=120),
    "delivery_state": Field(str, max_len=120),
    "latitude": Field(float, min_value=-90, max_value=90),
    "longitude": Field(float, min_value=-180, max_value=180),
    "payment_terms_days": Field(int, default=7, min_value=0, max_value=180),
    "valid_from": Field(dt.date),
    "valid_until": Field(dt.date),
    "notes": Field(str, max_len=500),
}

UPDATE_REQUIREMENT_SCHEMA = {
    **CREATE_REQUIREMENT_SCHEMA,
    "crop_id": Field(int, min_value=1),
    "required_quantity": Field(float, min_value=0.01),
}

REQUIREMENT_FILTER_SCHEMA = {
    "crop_id": Field(int, min_value=1),
    "status": Field(str, choices=STATUSES),
    "district": Field(str, max_len=120),
    "buyer_type": Field(str, choices=BUYER_TYPES),
    "buyer_id": Field(int, min_value=1),
    "order_by": Field(str, max_len=40),
}
