"""Vehicle registered by a transporter."""
from dataclasses import dataclass

from app.models import BaseModel


@dataclass
class Vehicle(BaseModel):
    BOOL_FIELDS = ("is_available",)

    id: int = None
    transporter_id: int = None
    vehicle_type: str = None
    vehicle_number: str = None
    capacity_tonnes: float = None
    service_area: str = None
    rate_per_km: float = None
    verification_status: str = "UNVERIFIED"
    is_available: int = 1
    created_at: str = None
    updated_at: str = None