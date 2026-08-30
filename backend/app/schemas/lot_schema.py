"""Request shapes for lots."""
import datetime as dt

from app.models.crop import UNITS
from app.models.lot import GRADES, STATUSES
from app.schemas import Field

CREATE_LOT_SCHEMA = {
    "crop_id": Field(int, required=True, min_value=1),
    "variety": Field(str, max_len=120),
    "quantity": Field(float, required=True, min_value=0.01),
    "unit": Field(str, choices=UNITS),
    "grade": Field(str, choices=GRADES, default="B"),
    "moisture_percent": Field(float, min_value=0, max_value=100),
    "expected_price": Field(float, min_value=0),
    "harvest_date": Field(dt.date),
    "available_from": Field(dt.date),
    "available_until": Field(dt.date),
    "village": Field(str, max_len=120),
    "district": Field(str, max_len=120),
    "state": Field(str, max_len=120),
    "latitude": Field(float, min_value=-90, max_value=90),
    "longitude": Field(float, min_value=-180, max_value=180),
    "notes": Field(str, max_len=500),
}

UPDATE_LOT_SCHEMA = {
    **{key: field for key, field in CREATE_LOT_SCHEMA.items()},
    "crop_id": Field(int, min_value=1),
    "quantity": Field(float, min_value=0.01),
}

LOT_FILTER_SCHEMA = {
    "crop_id": Field(int, min_value=1),
    "status": Field(str, choices=STATUSES),
    "district": Field(str, max_len=120),
    "state": Field(str, max_len=120),
    "grade": Field(str, choices=GRADES),
    "min_quantity": Field(float, min_value=0),
    "max_quantity": Field(float, min_value=0),
    "available_from": Field(dt.date),
    "order_by": Field(str, max_len=40),
}

SET_STATUS_SCHEMA = {"status": Field(str, required=True, choices=STATUSES)}

WITHDRAW_SCHEMA = {"reason": Field(str, max_len=500)}
