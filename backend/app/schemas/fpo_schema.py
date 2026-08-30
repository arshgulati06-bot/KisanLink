"""Request shapes for FPO profiles, membership and aggregation."""
import datetime as dt

from app.models.fpo_member import MEMBER_ROLES, MEMBER_STATUSES
from app.schemas import Field, PHONE_PATTERN

FPO_PROFILE_SCHEMA = {
    "fpo_name": Field(str, min_len=2, max_len=180),
    "registration_number": Field(str, max_len=80),
    "district": Field(str, max_len=120),
    "state": Field(str, max_len=120),
    "latitude": Field(float, min_value=-90, max_value=90),
    "longitude": Field(float, min_value=-180, max_value=180),
    "contact_person": Field(str, max_len=120),
}

ADD_MEMBER_SCHEMA = {
    "farmer_id": Field(int, min_value=1),
    "phone": Field(str, pattern=PHONE_PATTERN),
    "member_role": Field(str, choices=MEMBER_ROLES, default="MEMBER"),
}

UPDATE_MEMBER_SCHEMA = {
    "member_role": Field(str, choices=MEMBER_ROLES),
    "status": Field(str, choices=MEMBER_STATUSES),
}

AGGREGATE_SCHEMA = {
    "lot_ids": Field(list, required=True, item_type=int, min_len=2),
    "variety": Field(str, max_len=120),
    "expected_price": Field(float, min_value=0),
    "available_from": Field(dt.date),
    "available_until": Field(dt.date),
}

CANDIDATES_SCHEMA = {"crop_id": Field(int, required=True, min_value=1)}
