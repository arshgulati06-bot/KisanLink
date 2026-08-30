"""
Market intelligence: prices, arrivals, trends and nearby-market comparison.

Everything returned from here carries its source, so the frontend can label a
government-published price differently from a manually entered demo row. The
project rule is firm: demo data is never presented as real data.
"""
import datetime as dt

from app.models.market_data import VERIFIED_SOURCES
from app.repositories.crop_repository import crop_repository
from app.repositories.market_repository import (
    market_data_repository,
    market_repository,
)
from app.services import maps_service
from app.utils.responses import NotFoundError, ValidationError
from app.utils.units import convert_price
from ml.forecast_model import moving_average, summarise_arrivals

DEFAULT_TREND_DAYS = 30


def list_markets(query=None, district=None, state=None, market_type=None,
                 include_inactive=False, page=1, page_size=50, order_by=None):
    markets, total = market_repository.search(
        query=query,
        district=district,
        state=state,
        market_type=market_type,
        active_only=not include_inactive,
        page=page,
        page_size=page_size,
        order_by=order_by,
    )
    return [market.to_dict() for market in markets], total


def get_market(market_id):
    market = market_repository.find_by_id(market_id)
    if not market:
        raise NotFoundError("Market not found.")
    return market


def create_market(data):
    market_id = market_repository.insert(data)
    return market_repository.find_by_id(market_id).to_dict()


def nearby_markets(latitude=None, longitude=None, district=None, state=None,
                   crop_id=None, limit=10, max_distance_km=200):
    """
    Markets near a location, with each one's latest price for the crop.

    This is the comparison view: the farmer sees several markets at once rather
    than a single number, which is what price discovery actually requires.
    """
    origin = {
        "latitude": latitude,
        "longitude": longitude,
        "district": district,
        "state": state,
    }
    candidates = [market.to_dict() for market in market_repository.with_coordinates(state)]
    if not candidates:
        markets, _ = market_repository.search(district=district, state=state, page_size=limit)
        candidates = [market.to_dict() for market in markets]

    ranked = maps_service.nearest(origin, candidates, limit=limit, max_distance_km=max_distance_km)

    if crop_id:
        for market in ranked:
            latest = market_data_repository.latest_for(market["id"], crop_id)
            market["latest_price"] = latest.to_dict() if latest else None
            market["price_available"] = latest is not None
    return ranked


def latest_prices(crop_id, district=None, state=None, limit=50):
    """Newest observation per market for one crop, highest modal price first."""
    crop = crop_repository.find_by_id(crop_id)
    if not crop:
        raise NotFoundError("Crop not found.")
    rows = market_data_repository.latest_prices_for_crop(
        crop_id, district=district, state=state, limit=limit
    )
    for row in rows:
        row["arrival_available"] = row.get("arrival_quantity") is not None
        row["is_official_source"] = row.get("source") in VERIFIED_SOURCES
    return {
        "crop": crop.to_dict(),
        "markets_reporting": len(rows),
        "prices": rows,
        "data_note": _source_note(rows),
    }


def _source_note(rows):
    """One honest sentence about where these numbers came from."""
    if not rows:
        return "No price data has been loaded for this crop yet."
    sources = {row.get("source") for row in rows}
    if sources <= set(VERIFIED_SOURCES):
        return "Prices sourced from official/open government market data."
    if sources & set(VERIFIED_SOURCES):
        return (
            "Mixed sources: some prices come from official/open government data and "
            "some are platform-entered or demonstration rows. Check each row's source."
        )
    return (
        "These prices are platform-entered or demonstration data, "
        "not official published market prices."
    )


def price_trend(crop_id, market_id=None, days=DEFAULT_TREND_DAYS, variety=None):
    """
    Historical price series for charting, with a 7-day smoothing line.

    When a single market has too little history, the series falls back to the
    daily average across every reporting market and says so.
    """
    crop = crop_repository.find_by_id(crop_id)
    if not crop:
        raise NotFoundError("Crop not found.")

    scope = "MARKET"
    market = None
    if market_id:
        market = get_market(market_id)
        observations = market_data_repository.history(market_id, crop_id, days=days, variety=variety)
        series = [
            {
                "price_date": str(row.price_date)[:10],
                "modal_price": float(row.modal_price),
                "min_price": float(row.min_price) if row.min_price is not None else None,
                "max_price": float(row.max_price) if row.max_price is not None else None,
                "arrival_quantity": float(row.arrival_quantity)
                if row.arrival_quantity is not None
                else None,
                "source": row.source,
            }
            for row in observations
        ]
        if len(series) < 3:
            scope = "ALL_MARKETS"
            series = _crop_wide_series(crop_id, days)
    else:
        scope = "ALL_MARKETS"
        series = _crop_wide_series(crop_id, days)

    prices = [point["modal_price"] for point in series]
    smoothed = moving_average(prices, window=7) if prices else []
    for point, value in zip(series, smoothed):
        point["moving_average_7d"] = round(value, 2)

    change_percent = None
    if len(prices) >= 2 and prices[0]:
        change_percent = round(100.0 * (prices[-1] - prices[0]) / prices[0], 2)

    return {
        "crop": crop.to_dict(),
        "market": market.to_dict() if market else None,
        "scope": scope,
        "scope_note": (
            "Series for the selected market."
            if scope == "MARKET"
            else "Daily average across all reporting markets, "
            "because the selected market has too few observations."
        ),
        "days_requested": days,
        "data_points": len(series),
        "series": series,
        "period_change_percent": change_percent,
        "arrivals": summarise_arrivals(series),
    }


def _crop_wide_series(crop_id, days):
    rows = market_data_repository.crop_history_all_markets(crop_id, days=days)
    return [
        {
            "price_date": str(row["price_date"])[:10],
            "modal_price": round(float(row["modal_price"]), 2),
            "arrival_quantity": float(row["arrival_quantity"])
            if row.get("arrival_quantity") is not None
            else None,
            "market_count": int(row.get("market_count") or 0),
            "source": "AGGREGATED",
        }
        for row in rows
    ]


def benchmark_price(crop_id, district=None, target_unit="QUINTAL"):
    """
    One reference price for the crop, converted into the caller's unit.

    Used by the matching engine to judge whether an offer is good in absolute
    terms rather than only relative to the other offers on the table.
    """
    result = market_data_repository.benchmark_price(crop_id, district=district)
    price = result.get("avg_price")
    if price is None:
        return {
            "available": False,
            "price": None,
            "unit": target_unit,
            "reason": "No recent market price is available for this crop.",
        }
    # Market prices are published per quintal in the datasets we ingest.
    converted = convert_price(float(price), "QUINTAL", target_unit)
    return {
        "available": True,
        "price": round(converted, 2),
        "unit": target_unit,
        "source_unit": "QUINTAL",
        "observations": int(result.get("observations") or 0),
        "as_of": str(result.get("latest_date"))[:10] if result.get("latest_date") else None,
        "district_scope": district or "ALL",
    }


def arrivals(market_id, crop_id, days=30):
    """Arrival volume series, or an explicit statement that none is published."""
    get_market(market_id)
    rows = market_data_repository.arrivals_series(market_id, crop_id, days=days)
    summary = summarise_arrivals(rows)
    return {
        "market_id": market_id,
        "crop_id": crop_id,
        "series": [
            {
                "price_date": str(row["price_date"])[:10],
                "arrival_quantity": float(row["arrival_quantity"])
                if row.get("arrival_quantity") is not None
                else None,
                "arrival_unit": row.get("arrival_unit"),
                "modal_price": float(row["modal_price"]) if row.get("modal_price") else None,
            }
            for row in rows
        ],
        "summary": summary,
    }


def record_observation(data):
    """
    Store one price observation, replacing that market/crop/day if reloaded.

    Used by the admin ingest endpoint and by the data pipeline.
    """
    if not market_repository.find_by_id(data["market_id"]):
        raise NotFoundError("Market not found.")
    if not crop_repository.find_by_id(data["crop_id"]):
        raise NotFoundError("Crop not found.")
    minimum, maximum = data.get("min_price"), data.get("max_price")
    if minimum is not None and maximum is not None and float(minimum) > float(maximum):
        raise ValidationError("'min_price' cannot be greater than 'max_price'.")
    if isinstance(data.get("price_date"), (dt.date, dt.datetime)):
        data["price_date"] = data["price_date"].strftime("%Y-%m-%d")
    record_id, created = market_data_repository.upsert_observation(data)
    return market_data_repository.find_by_id(record_id).to_dict(), created


def bulk_record_observations(rows):
    """Load many observations, reporting per-row failures instead of aborting."""
    created, updated, errors = 0, 0, []
    for index, row in enumerate(rows):
        try:
            _, was_created = record_observation(dict(row))
            created += 1 if was_created else 0
            updated += 0 if was_created else 1
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the load
            errors.append({"row": index, "error": str(exc)})
    return {"created": created, "updated": updated, "failed": len(errors), "errors": errors}


def market_overview(crop_id, district=None, state=None, limit=10):
    """
    The market-intelligence panel for one crop: best price, spread and arrivals.

    The spread between the highest and lowest reporting market is the clearest
    single measure of the information asymmetry this project targets.
    """
    data = latest_prices(crop_id, district=district, state=state, limit=limit)
    prices = [float(row["modal_price"]) for row in data["prices"] if row.get("modal_price")]
    overview = {
        **data,
        "highest_price": round(max(prices), 2) if prices else None,
        "lowest_price": round(min(prices), 2) if prices else None,
        "average_price": round(sum(prices) / len(prices), 2) if prices else None,
    }
    if prices and min(prices) > 0:
        spread = max(prices) - min(prices)
        overview["price_spread"] = round(spread, 2)
        overview["price_spread_percent"] = round(100.0 * spread / min(prices), 2)
        overview["spread_note"] = (
            f"The best and worst reporting markets differ by Rs {spread:,.0f} per quintal. "
            "Comparing markets before selling is worth this much."
        )
    return overview
