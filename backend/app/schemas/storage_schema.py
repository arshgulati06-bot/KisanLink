"""Request shapes for storage facilities and holding-cost estimates."""
from app.models.crop import UNITS
from app.models.storage_facility import FACILITY_TYPES
from app.schemas import Field, PHONE_PATTERN

CREATE_FACILITY_SCHEMA = {
    "name": Field(str, required=True, min_len=2, max_len=180),
    "facility_type": Field(str, choices=FACILITY_TYPES, default="WAREHOUSE"),
    "operator_name": Field(str, max_len=180),
    "district": Field(str, max_len=120),
    "state": Field(str, default="Maharashtra", max_len=120),
    "address": Field(str, max_len=255),
    "latitude": Field(float, min_value=-90, max_value=90),
    "longitude": Field(float, min_value=-180, max_value=180),
    "capacity_tonnes": Field(float, min_value=0),
    "available_capacity_tonnes": Field(float, min_value=0),
    "cost_per_tonne_per_day": Field(float, min_value=0),
    "has_cold_storage": Field(bool, default=False),
    "offers_warehouse_receipt": Field(bool, default=False),
    "contact_phone": Field(str, pattern=PHONE_PATTERN),
}

FACILITY_FILTER_SCHEMA = {
    "district": Field(str, max_len=120),
    "state": Field(str, max_len=120),
    "facility_type": Field(str, choices=FACILITY_TYPES),
    "cold_only": Field(bool, default=False),
    "min_available_tonnes": Field(float, min_value=0),
    "order_by": Field(str, max_len=40),
}

NEARBY_FACILITY_SCHEMA = {
    "latitude": Field(float, min_value=-90, max_value=90),
    "longitude": Field(float, min_value=-180, max_value=180),
    "district": Field(str, max_len=120),
    "state": Field(str, max_len=120),
    "required_tonnes": Field(float, min_value=0),
    "cold_storage": Field(bool, default=False),
    "limit": Field(int, default=10, min_value=1, max_value=50),
    "max_distance_km": Field(float, default=150, min_value=1, max_value=1000),
}

STORAGE_ESTIMATE_SCHEMA = {
    "quantity": Field(float, required=True, min_value=0.01),
    "unit": Field(str, choices=UNITS, default="QUINTAL"),
    "days": Field(int, required=True, min_value=1, max_value=365),
    "facility_id": Field(int, min_value=1),
    "price_per_unit": Field(float, min_value=0),
    "is_perishable": Field(bool, default=False),
}
