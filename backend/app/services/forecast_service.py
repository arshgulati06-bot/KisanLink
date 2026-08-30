"""
Price forecasting.

Thin wrapper around ``ml/forecast_model.py`` that pulls history from the
database, caches the result and - most importantly - refuses to answer when the
history is too thin. "Insufficient historical data" is a valid, expected output
of this service, not an error.
"""
import datetime as dt

from app.config.settings import settings
from app.repositories.crop_repository import crop_repository
from app.repositories.market_repository import (
    market_data_repository,
    market_repository,
    price_forecast_repository,
)
from app.utils.responses import NotFoundError, ValidationError
from ml.forecast_model import forecast_prices


def forecast_for(crop_id, market_id=None, horizon_days=None, variety=None, store=True):
    """
    Forecast the modal price for a crop, optionally at one market.

    Args:
        crop_id: crop to forecast.
        market_id: restrict history to one market. When that market has too
            little history the crop-wide series is used instead, and the
            response says which was used.
        horizon_days: days ahead. Capped by FORECAST_MAX_HORIZON_DAYS.
        store: cache the result in ``price_forecasts``.
    """
    crop = crop_repository.find_by_id(crop_id)
    if not crop:
        raise NotFoundError("Crop not found.")

    horizon_days = int(horizon_days or settings.FORECAST_DEFAULT_HORIZON_DAYS)
    if horizon_days < 1 or horizon_days > settings.FORECAST_MAX_HORIZON_DAYS:
        raise ValidationError(
            f"'horizon_days' must be between 1 and {settings.FORECAST_MAX_HORIZON_DAYS}."
        )

    scope = "ALL_MARKETS"
    market = None
    observations = []

    if market_id:
        market = market_repository.find_by_id(market_id)
        if not market:
            raise NotFoundError("Market not found.")
        observations = [
            {"price_date": row.price_date, "modal_price": row.modal_price,
             "arrival_quantity": row.arrival_quantity}
            for row in market_data_repository.history(market_id, crop_id, days=180, variety=variety)
        ]
        scope = "MARKET"

    if len(observations) < settings.MIN_FORECAST_HISTORY_POINTS:
        # One market may be sparse while the crop as a whole is well covered.
        wider = market_data_repository.crop_history_all_markets(crop_id, days=180)
        if len(wider) > len(observations):
            observations = wider
            scope = "ALL_MARKETS"

    result = forecast_prices(
        observations,
        horizon_days=horizon_days,
        min_points=settings.MIN_FORECAST_HISTORY_POINTS,
    )
    result["scope"] = scope
    result["crop"] = crop.to_dict()
    result["market"] = market.to_dict() if market else None
    result["scope_note"] = (
        "Based on this market's own price history."
        if scope == "MARKET"
        else "Based on the daily average across all reporting markets, "
        "because a single market did not have enough history."
    )

    if store and result.get("available") and market_id:
        _cache(market_id, crop_id, horizon_days, result)
    return result


def _cache(market_id, crop_id, horizon_days, result):
    price_forecast_repository.insert(
        {
            "market_id": market_id,
            "crop_id": crop_id,
            "forecast_date": result["projections"][-1]["forecast_date"],
            "horizon_days": horizon_days,
            "forecast_price": result["forecast_price"],
            "lower_bound": result["lower_bound"],
            "upper_bound": result["upper_bound"],
            "confidence": result["confidence"],
            "method": result["method"],
            "data_points": result["data_points"],
            "notes": result["notes"][:250],
            "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


def latest_cached(market_id, crop_id, horizon_days=None):
    horizon_days = int(horizon_days or settings.FORECAST_DEFAULT_HORIZON_DAYS)
    record = price_forecast_repository.latest_for(market_id, crop_id, horizon_days)
    return record.to_dict() if record else None


def data_readiness(crop_id, market_id=None):
    """
    Report whether forecasting is even possible yet.

    Useful during the data-verification phase: it answers "do we have enough
    history to build this feature?" without producing a forecast.
    """
    if market_id:
        points = len(market_data_repository.history(market_id, crop_id, days=365))
    else:
        points = len(market_data_repository.crop_history_all_markets(crop_id, days=365))
    required = settings.MIN_FORECAST_HISTORY_POINTS
    return {
        "crop_id": crop_id,
        "market_id": market_id,
        "observations": points,
        "minimum_required": required,
        "forecast_possible": points >= required,
        "message": (
            f"{points} observations available; forecasting is enabled."
            if points >= required
            else f"Only {points} observations available; {required} are needed before a "
            "forecast can be shown."
        ),
    }
