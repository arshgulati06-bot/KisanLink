"""
One observed price (and, where published, arrival volume) for a market, crop
and day.

``arrival_quantity`` is nullable on purpose: when the source does not publish
arrivals we say so rather than storing a misleading zero.
"""
from dataclasses import dataclass

from app.models import BaseModel

AGMARKNET = "AGMARKNET"
DATA_GOV_IN = "DATA_GOV_IN"
ENAM = "ENAM"
MANUAL = "MANUAL"
SEED_DEMO = "SEED_DEMO"
SOURCES = (AGMARKNET, DATA_GOV_IN, ENAM, MANUAL, SEED_DEMO)

#: Sources that are official/open government data rather than platform entries.
VERIFIED_SOURCES = (AGMARKNET, DATA_GOV_IN, ENAM)


@dataclass
class MarketData(BaseModel):
    FLOAT_FIELDS = ("min_price", "max_price", "modal_price", "arrival_quantity")

    id: int = None
    market_id: int = None
    crop_id: int = None
    variety: str = "General"
    price_date: str = None
    min_price: float = None
    max_price: float = None
    modal_price: float = None
    arrival_quantity: float = None
    arrival_unit: str = "TONNE"
    price_unit: str = "QUINTAL"
    source: str = MANUAL
    created_at: str = None

    def to_dict(self, extra=None):
        data = super().to_dict(extra)
        data["arrival_available"] = self.arrival_quantity is not None
        data["is_official_source"] = self.source in VERIFIED_SOURCES
        return data
