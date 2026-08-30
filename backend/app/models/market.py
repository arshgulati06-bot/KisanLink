"""A physical or electronic marketplace where the crop can be sold."""
from dataclasses import dataclass

from app.models import BaseModel

APMC = "APMC"
PRIVATE = "PRIVATE"
ENAM = "ENAM"
FARMER_MARKET = "FARMER_MARKET"
MARKET_TYPES = (APMC, PRIVATE, ENAM, FARMER_MARKET, "OTHER")


@dataclass
class Market(BaseModel):
    BOOL_FIELDS = ("is_active",)
    FLOAT_FIELDS = ("latitude", "longitude")

    id: int = None
    name: str = None
    market_code: str = None
    market_type: str = APMC
    district: str = None
    state: str = "Maharashtra"
    latitude: float = None
    longitude: float = None
    address: str = None
    contact_phone: str = None
    is_active: int = 1
    created_at: str = None
