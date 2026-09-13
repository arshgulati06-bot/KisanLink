"""Request shapes for transport estimates and requests."""
import datetime as dt

from app.models.crop import UNITS
from app.models.logistics_request import STATUSES, VEHICLE_TYPES
from app.models.logistics_incident import INCIDENT_TYPES, INCIDENT_STATUSES
from app.schemas import Field, PHONE_PATTERN


# ---------------------------------------------------------------------------
# Transport estimate
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Logistics requests
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Transporter management
# ---------------------------------------------------------------------------

CREATE_TRANSPORTER_SCHEMA = {
    "business_name": Field(str, required=True, max_len=180),
    "phone": Field(str, pattern=PHONE_PATTERN),
    "district": Field(str, max_len=120),
    "state": Field(str, max_len=120),
}


TRANSPORTER_FILTER_SCHEMA = {
    "district": Field(str, max_len=120),
    "verification_status": Field(str, max_len=30),
    "q": Field(str, max_len=120),
    "order_by": Field(str, max_len=40),
}


# ---------------------------------------------------------------------------
# Vehicle management
# ---------------------------------------------------------------------------

CREATE_VEHICLE_SCHEMA = {
    "transporter_id": Field(int, required=True, min_value=1),
    "vehicle_type": Field(str, required=True, choices=VEHICLE_TYPES),
    "vehicle_number": Field(str, required=True, max_len=30),
    "capacity_tonnes": Field(float, required=True, min_value=0.1),
    "service_area": Field(str, max_len=255),
    "rate_per_km": Field(float, min_value=0),
}


VEHICLE_FILTER_SCHEMA = {
    "vehicle_type": Field(str, choices=VEHICLE_TYPES),
    "transporter_id": Field(int, min_value=1),
    "min_capacity": Field(float, min_value=0),
}


# ---------------------------------------------------------------------------
# Transport assignment / reassignment
# ---------------------------------------------------------------------------

REASSIGN_SCHEMA = {
    "transporter_id": Field(int, required=True, min_value=1),
    "vehicle_id": Field(int, required=True, min_value=1),
}


# ---------------------------------------------------------------------------
# ETA and route progress
# ---------------------------------------------------------------------------

ETA_UPDATE_SCHEMA = {
    "eta_minutes": Field(float, required=True, min_value=0),
    "route_status": Field(str, max_len=30),
    "route_progress_percent": Field(
        float,
        min_value=0,
        max_value=100,
    ),
}


# ---------------------------------------------------------------------------
# Logistics incidents
# ---------------------------------------------------------------------------

CREATE_INCIDENT_SCHEMA = {
    "incident_type": Field(
        str,
        required=True,
        choices=INCIDENT_TYPES,
    ),
    "description": Field(str, required=True, max_len=500),
}


UPDATE_INCIDENT_SCHEMA = {
    "status": Field(
        str,
        required=True,
        choices=INCIDENT_STATUSES,
    ),
    "resolution_notes": Field(str, max_len=500),
}