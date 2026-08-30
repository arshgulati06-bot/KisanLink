"""Request shapes for markets, price observations and trends."""
import datetime as dt

from app.models.market import MARKET_TYPES
from app.models.market_data import SOURCES
from app.schemas import Field

CREATE_MARKET_SCHEMA = {
    "name": Field(str, required=True, min_len=2, max_len=180),
    "market_code": Field(str, max_len=60),
    "market_type": Field(str, choices=MARKET_TYPES, default="APMC"),
    "district": Field(str, max_len=120),
    "state": Field(str, default="Maharashtra", max_len=120),
    "latitude": Field(float, min_value=-90, max_value=90),
    "longitude": Field(float, min_value=-180, max_value=180),
    "address": Field(str, max_len=255),
    "contact_phone": Field(str, max_len=20),
}

MARKET_FILTER_SCHEMA = {
    "q": Field(str, max_len=120),
    "district": Field(str, max_len=120),
    "state": Field(str, max_len=120),
    "market_type": Field(str, choices=MARKET_TYPES),
    "include_inactive": Field(bool, default=False),
    "order_by": Field(str, max_len=40),
}

NEARBY_SCHEMA = {
    "latitude": Field(float, min_value=-90, max_value=90),
    "longitude": Field(float, min_value=-180, max_value=180),
    "district": Field(str, max_len=120),
    "state": Field(str, max_len=120),
    "crop_id": Field(int, min_value=1),
    "limit": Field(int, default=10, min_value=1, max_value=50),
    "max_distance_km": Field(float, default=200, min_value=1, max_value=2000),
}

PRICE_QUERY_SCHEMA = {
    "crop_id": Field(int, required=True, min_value=1),
    "district": Field(str, max_len=120),
    "state": Field(str, max_len=120),
    "limit": Field(int, default=50, min_value=1, max_value=200),
}

TREND_QUERY_SCHEMA = {
    "crop_id": Field(int, required=True, min_value=1),
    "market_id": Field(int, min_value=1),
    "days": Field(int, default=30, min_value=2, max_value=365),
    "variety": Field(str, max_len=120),
}

RECORD_PRICE_SCHEMA = {
    "market_id": Field(int, required=True, min_value=1),
    "crop_id": Field(int, required=True, min_value=1),
    "variety": Field(str, default="General", max_len=120),
    "price_date": Field(dt.date, required=True),
    "min_price": Field(float, min_value=0),
    "max_price": Field(float, min_value=0),
    "modal_price": Field(float, required=True, min_value=0),
    "arrival_quantity": Field(float, min_value=0, nullable=True),
    "arrival_unit": Field(str, default="TONNE", max_len=20),
    "price_unit": Field(str, default="QUINTAL", max_len=20),
    "source": Field(str, choices=SOURCES, default="MANUAL"),
}

ARRIVALS_QUERY_SCHEMA = {
    "crop_id": Field(int, required=True, min_value=1),
    "days": Field(int, default=30, min_value=2, max_value=365),
}
