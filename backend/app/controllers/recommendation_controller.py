"""
Recommendation, matching and forecasting endpoints.

This is the hero API: one call returns the ranked options, the net realization
for each, the sale-window advice and the reasons behind the top choice.
"""
from flask import request

from app.controllers import body, query
from app.middleware.auth_middleware import login_required
from app.schemas.recommendation_schema import (
    FORECAST_SCHEMA,
    MATCH_SCHEMA,
    RECOMMEND_SCHEMA,
    SALE_WINDOW_SCHEMA,
)
from app.services import forecast_service, matching_service, recommendation_service
from app.utils.responses import ValidationError, success


@login_required
def recommend():
    data = body(RECOMMEND_SCHEMA)
    return success(
        recommendation_service.recommend_for_lot(
            data["lot_id"],
            horizon_days=data.get("horizon_days"),
            include_markets=data.get("include_markets", True),
            limit=data.get("limit", 10),
            store=data.get("store", True),
        )
    )


@login_required
def for_lot(lot_id):
    return success(
        recommendation_service.recommend_for_lot(
            lot_id, horizon_days=request.args.get("horizon_days"), store=False
        )
    )


@login_required
def latest(lot_id):
    return success(recommendation_service.latest_recommendation(lot_id))


@login_required
def history(lot_id):
    return success(recommendation_service.recommendation_history(lot_id))


@login_required
def sale_window():
    data = body(SALE_WINDOW_SCHEMA)
    return success(
        recommendation_service.sale_window_only(data["lot_id"], data.get("horizon_days"))
    )


@login_required
def match():
    data = body(MATCH_SCHEMA)
    limit = data.get("limit", 10)
    if data.get("lot_id"):
        return success(matching_service.match_lot(data["lot_id"], limit=limit))
    if data.get("requirement_id"):
        return success(matching_service.match_requirement(data["requirement_id"], limit=limit))
    raise ValidationError("Provide either 'lot_id' or 'requirement_id'.")


def forecast():
    filters = query(FORECAST_SCHEMA)
    if not filters.get("crop_id"):
        raise ValidationError("'crop_id' is required.")
    return success(
        forecast_service.forecast_for(
            filters["crop_id"],
            market_id=filters.get("market_id"),
            horizon_days=filters.get("horizon_days"),
            variety=filters.get("variety"),
            store=False,
        )
    )


def readiness():
    crop_id = request.args.get("crop_id", type=int)
    if not crop_id:
        raise ValidationError("'crop_id' is required.")
    return success(
        forecast_service.data_readiness(crop_id, market_id=request.args.get("market_id", type=int))
    )
