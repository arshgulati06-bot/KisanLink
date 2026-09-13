"""Transporter profile linked to a user account."""
from dataclasses import dataclass

from app.models import BaseModel


@dataclass
class Transporter(BaseModel):
    BOOL_FIELDS = ("is_available",)

    id: int = None
    user_id: int = None
    business_name: str = None
    phone: str = None
    district: str = None
    state: str = "Maharashtra"
    verification_status: str = "UNVERIFIED"
    rating: float = 0.0
    reliability_score: float = 40.0
    total_trips: int = 0
    completed_trips: int = 0
    is_available: int = 1
    created_at: str = None
    updated_at: str = None