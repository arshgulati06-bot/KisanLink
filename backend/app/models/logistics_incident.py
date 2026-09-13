"""Incident reported against a logistics request."""
from dataclasses import dataclass

from app.models import BaseModel


VEHICLE_BREAKDOWN = "VEHICLE_BREAKDOWN"
ACCIDENT = "ACCIDENT"
ROUTE_BLOCKED = "ROUTE_BLOCKED"
DELAY = "DELAY"
VEHICLE_UNAVAILABLE = "VEHICLE_UNAVAILABLE"
OTHER = "OTHER"

INCIDENT_TYPES = (
    VEHICLE_BREAKDOWN,
    ACCIDENT,
    ROUTE_BLOCKED,
    DELAY,
    VEHICLE_UNAVAILABLE,
    OTHER,
)


OPEN = "OPEN"
IN_PROGRESS = "IN_PROGRESS"
RESOLVED = "RESOLVED"
CANCELLED = "CANCELLED"

INCIDENT_STATUSES = (
    OPEN,
    IN_PROGRESS,
    RESOLVED,
    CANCELLED,
)


@dataclass
class LogisticsIncident(BaseModel):
    id: int = None
    logistics_request_id: int = None
    incident_type: str = None
    description: str = None
    status: str = OPEN
    reported_by_user_id: int = None
    reported_at: str = None
    resolved_at: str = None
    resolution_notes: str = None
    created_at: str = None
    updated_at: str = None