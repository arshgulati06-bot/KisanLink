"""Farmer Producer Organisation account details."""
from dataclasses import dataclass

from app.models import BaseModel


@dataclass
class FpoProfile(BaseModel):
    FLOAT_FIELDS = ("latitude", "longitude")

    id: int = None
    user_id: int = None
    fpo_name: str = None
    registration_number: str = None
    district: str = None
    state: str = "Maharashtra"
    latitude: float = None
    longitude: float = None
    contact_person: str = None
    member_count: int = 0
    created_at: str = None
    updated_at: str = None
