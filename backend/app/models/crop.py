"""Commodity reference data."""
from dataclasses import dataclass

from app.models import BaseModel

CATEGORIES = (
    "VEGETABLE",
    "FRUIT",
    "CEREAL",
    "PULSE",
    "OILSEED",
    "SPICE",
    "FIBRE",
    "OTHER",
)

UNITS = ("QUINTAL", "KG", "TONNE", "DOZEN", "BAG")


@dataclass
class Crop(BaseModel):
    BOOL_FIELDS = ("is_perishable", "is_active")

    id: int = None
    name: str = None
    local_name: str = None
    category: str = "OTHER"
    default_unit: str = "QUINTAL"
    shelf_life_days: int = None
    is_perishable: int = 0
    grade_scale: str = "A,B,C"
    is_active: int = 1
    created_at: str = None

    @property
    def grades(self):
        return [g.strip().upper() for g in (self.grade_scale or "A,B,C").split(",") if g.strip()]
