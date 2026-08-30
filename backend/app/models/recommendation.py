"""
A stored snapshot of one run of the recommendation engine.

Keeping the full ranked comparison in ``payload_json`` means the advice a
farmer acted on can be reproduced later, which matters if the deal is disputed.
"""
import json
from dataclasses import dataclass

from app.models import BaseModel

SELL_NOW = "SELL_NOW"
CONSIDER_WAITING = "CONSIDER_WAITING"
MONITOR = "MONITOR"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
SALE_WINDOWS = (SELL_NOW, CONSIDER_WAITING, MONITOR, INSUFFICIENT_DATA)

OPTION_BUYER = "BUYER"
OPTION_MARKET = "MARKET"
OPTION_OFFER = "OFFER"


@dataclass
class Recommendation(BaseModel):
    FLOAT_FIELDS = ("estimated_net_realization",)

    id: int = None
    lot_id: int = None
    generated_at: str = None
    recommended_option_type: str = None
    recommended_option_id: int = None
    recommended_label: str = None
    estimated_net_realization: float = None
    sale_window: str = None
    sale_window_confidence: str = None
    option_count: int = 0
    payload_json: str = None

    def to_dict(self, extra=None):
        data = super().to_dict(extra)
        raw = data.pop("payload_json", None)
        try:
            data["payload"] = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            data["payload"] = None
        return data
