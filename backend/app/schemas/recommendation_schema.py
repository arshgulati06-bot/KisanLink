"""Request shapes for the recommendation and forecasting endpoints."""
from app.schemas import Field

RECOMMEND_SCHEMA = {
    "lot_id": Field(int, required=True, min_value=1),
    "horizon_days": Field(int, min_value=1, max_value=30),
    "include_markets": Field(bool, default=True),
    "limit": Field(int, default=10, min_value=1, max_value=50),
    "store": Field(bool, default=True),
}

MATCH_SCHEMA = {
    "lot_id": Field(int, min_value=1),
    "requirement_id": Field(int, min_value=1),
    "limit": Field(int, default=10, min_value=1, max_value=50),
}

FORECAST_SCHEMA = {
    "crop_id": Field(int, required=True, min_value=1),
    "market_id": Field(int, min_value=1),
    "horizon_days": Field(int, min_value=1, max_value=30),
    "variety": Field(str, max_len=120),
}

SALE_WINDOW_SCHEMA = {
    "lot_id": Field(int, required=True, min_value=1),
    "horizon_days": Field(int, min_value=1, max_value=30),
}
