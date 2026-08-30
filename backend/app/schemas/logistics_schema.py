"""Request shapes for transport estimates and requests."""
import datetime as dt

from app.models.crop import UNITS
from app.models.logistics_request import STATUSES, VEHICLE_TYPES
from app.schemas import Field, PHONE_PATTERN

ESTIMATE_SCHEMA = {
    "quantity": Field(float, required=True, min_value=0.01),
    "unit": Field(str, choices=UNITS, default="QUINTAL"),
    "distance_km": Field(float, min_value=0, max_value=5000),
    "from_latitude": Field(float, min_value=-90, max_value=90),
    "from_longitude": Field(float, min_value=-180, max_value=180),
    "from_district": Field(str, max_len=120),
    "to_latitude": Field(float, min_value=-90, max_value=90),
    "to_longitude": Field(float, min_value=-180, max_value=180),
    "to_district": Field(str, max_len=120),
}

CREATE_REQUEST_SCHEMA = {
    "transaction_id": Field(int, min_value=1),
    "lot_id": Field(int, min_value=1),
    "pickup_address": Field(str, max_len=255),
    "pickup_district": Field(str, max_len=120),
    "pickup_latitude": Field(float, min_value=-90, max_value=90),
    "pickup_longitude": Field(float, min_value=-180, max_value=180),
    "drop_address": Field(str, max_len=255),
    "drop_district": Field(str, max_len=120),
    "drop_latitude": Field(float, min_value=-90, max_value=90),
    "drop_longitude": Field(float, min_value=-180, max_value=180),
    "vehicle_type": Field(str, choices=VEHICLE_TYPES),
    "quantity": Field(float, min_value=0.01),
    "unit": Field(str, choices=UNITS),
    "scheduled_date": Field(dt.date),
    "notes": Field(str, max_len=500),
}

UPDATE_STATUS_SCHEMA = {
    "status": Field(str, required=True, choices=STATUSES),
    "notes": Field(str, max_len=500),
    "actual_cost": Field(float, min_value=0),
}

ASSIGN_PROVIDER_SCHEMA = {
    "provider_name": Field(str, required=True, max_len=180),
    "provider_phone": Field(str, pattern=PHONE_PATTERN),
    "scheduled_date": Field(dt.date),
}

REQUEST_FILTER_SCHEMA = {
    "status": Field(str, choices=STATUSES),
    "transaction_id": Field(int, min_value=1),
    "lot_id": Field(int, min_value=1),
    "order_by": Field(str, max_len=40),
}
