"""A stored forecast produced by ml/forecast_model.py."""
from dataclasses import dataclass

from app.models import BaseModel

LINEAR_TREND = "LINEAR_TREND"
MOVING_AVERAGE = "MOVING_AVERAGE"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
CONFIDENCE_LEVELS = (LOW, MEDIUM, HIGH)


@dataclass
class PriceForecast(BaseModel):
    FLOAT_FIELDS = ("forecast_price", "lower_bound", "upper_bound")

    id: int = None
    market_id: int = None
    crop_id: int = None
    generated_at: str = None
    forecast_date: str = None
    horizon_days: int = None
    forecast_price: float = None
    lower_bound: float = None
    upper_bound: float = None
    confidence: str = LOW
    method: str = INSUFFICIENT_DATA
    data_points: int = 0
    notes: str = None
