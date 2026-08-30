"""Farm-level details attached to a FARMER account."""
from dataclasses import dataclass

from app.models import BaseModel


@dataclass
class FarmerProfile(BaseModel):
    FLOAT_FIELDS = ("latitude", "longitude", "land_size_acres")

    id: int = None
    user_id: int = None
    village: str = None
    district: str = None
    state: str = "Maharashtra"
    pincode: str = None
    latitude: float = None
    longitude: float = None
    land_size_acres: float = None
    primary_crops: str = None
    fpo_id: int = None
    created_at: str = None
    updated_at: str = None

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None
