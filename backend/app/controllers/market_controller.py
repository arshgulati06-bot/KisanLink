"""Market intelligence endpoints."""
from flask import request

from app.controllers import body, page_args, query
from app.middleware.role_middleware import admin_required
from app.schemas.market_schema import (
    ARRIVALS_QUERY_SCHEMA,
    CREATE_MARKET_SCHEMA,
    MARKET_FILTER_SCHEMA,
    NEARBY_SCHEMA,
    PRICE_QUERY_SCHEMA,
    RECORD_PRICE_SCHEMA,
    TREND_QUERY_SCHEMA,
)
from app.services import market_service
from app.utils.responses import ValidationError, created, paginated, success


def list_markets():
    page, page_size = page_args()
    filters = query(MARKET_FILTER_SCHEMA)
    items, total = market_service.list_markets(
        query=filters.get("q"),
        district=filters.get("district"),
        state=filters.get("state"),
        market_type=filters.get("market_type"),
        include_inactive=filters.get("include_inactive", False),
        page=page,
        page_size=page_size,
        order_by=filters.get("order_by"),
    )
    return paginated(items, page, page_size, total)


def get_market(market_id):
    return success(market_service.get_market(market_id).to_dict())


def nearby():
    filters = query(NEARBY_SCHEMA)
    if filters.get("latitude") is None and not filters.get("district"):
        raise ValidationError(
            "Provide either 'latitude' and 'longitude', or a 'district', to find nearby markets."
        )
    return success(
        market_service.nearby_markets(
            latitude=filters.get("latitude"),
            longitude=filters.get("longitude"),
            district=filters.get("district"),
            state=filters.get("state"),
            crop_id=filters.get("crop_id"),
            limit=filters.get("limit", 10),
            max_distance_km=filters.get("max_distance_km", 200),
        )
    )


def prices():
    filters = query(PRICE_QUERY_SCHEMA)
    if not filters.get("crop_id"):
        raise ValidationError("'crop_id' is required.")
    return success(
        market_service.latest_prices(
            filters["crop_id"],
            district=filters.get("district"),
            state=filters.get("state"),
            limit=filters.get("limit", 50),
        )
    )


def overview():
    filters = query(PRICE_QUERY_SCHEMA)
    if not filters.get("crop_id"):
        raise ValidationError("'crop_id' is required.")
    return success(
        market_service.market_overview(
            filters["crop_id"],
            district=filters.get("district"),
            state=filters.get("state"),
            limit=filters.get("limit", 10),
        )
    )


def trends():
    filters = query(TREND_QUERY_SCHEMA)
    if not filters.get("crop_id"):
        raise ValidationError("'crop_id' is required.")
    return success(
        market_service.price_trend(
            filters["crop_id"],
            market_id=filters.get("market_id"),
            days=filters.get("days", 30),
            variety=filters.get("variety"),
        )
    )


def arrivals(market_id):
    filters = query(ARRIVALS_QUERY_SCHEMA)
    if not filters.get("crop_id"):
        raise ValidationError("'crop_id' is required.")
    return success(
        market_service.arrivals(market_id, filters["crop_id"], days=filters.get("days", 30))
    )


def benchmark():
    crop_id = request.args.get("crop_id", type=int)
    if not crop_id:
        raise ValidationError("'crop_id' is required.")
    return success(
        market_service.benchmark_price(
            crop_id,
            district=request.args.get("district"),
            target_unit=request.args.get("unit", "QUINTAL"),
        )
    )


@admin_required
def create_market():
    return created(market_service.create_market(body(CREATE_MARKET_SCHEMA)), message="Market added.")


@admin_required
def record_price():
    record, was_created = market_service.record_observation(body(RECORD_PRICE_SCHEMA))
    return success(
        record,
        message="Price observation recorded." if was_created else "Price observation updated.",
        status_code=201 if was_created else 200,
    )


@admin_required
def bulk_record_prices():
    payload = request.get_json(silent=True) or {}
    rows = payload.get("records")
    if not isinstance(rows, list) or not rows:
        raise ValidationError("Send a non-empty 'records' array.")
    return success(market_service.bulk_record_observations(rows), message="Bulk load complete.")
