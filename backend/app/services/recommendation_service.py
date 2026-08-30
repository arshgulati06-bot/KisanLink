"""
The hero feature.

Given one lot, this service answers the whole question the project is built
around: *what should this farmer do with this crop right now, and why?*

It does that by putting every selling channel on the same footing - mandis,
processors, institutional buyers, traders, and any live offer already on the
table - costing each one out to a NET realization, ranking them, deciding
whether now is the right time to sell, and writing down the reasons.
"""
import datetime as dt
import json

from app.config.settings import settings
from app.models.crop import Crop
from app.repositories.crop_repository import crop_repository
from app.repositories.lot_repository import lot_repository
from app.repositories.market_repository import market_repository
from app.repositories.offer_repository import offer_repository
from app.repositories.trust_repository import recommendation_repository
from app.repositories.user_repository import buyer_profile_repository
from app.services import (
    forecast_service,
    logistics_service,
    maps_service,
    market_service,
    matching_service,
    storage_service,
)
from app.utils.responses import NotFoundError
from app.utils.units import convert_price
from ml.recommendation_engine import (
    compare_top_options,
    evaluate_options,
    explain_recommendation,
    net_adjusted_weights,
    sale_window_advice,
)

#: How many nearby mandis to price up alongside the buyer options.
MARKET_OPTION_LIMIT = 5

#: Display names for market types. Written out rather than title-cased so
#: acronyms stay capitalised.
MARKET_TYPE_LABELS = {
    "APMC": "APMC market yard",
    "ENAM": "e-NAM electronic market",
    "PRIVATE": "Private market",
    "FARMER_MARKET": "Farmer market",
    "OTHER": "Market",
}


def recommend_for_lot(lot_id, horizon_days=None, include_markets=True, limit=10, store=True):
    """
    Produce the full recommendation for a lot.

    Args:
        lot_id: the lot to advise on.
        horizon_days: the waiting window to evaluate for the sale-window advice.
        include_markets: also price up nearby mandis, not just buyers.
        limit: how many ranked options to return.
        store: save a snapshot so the advice can be reproduced later.
    """
    lot = lot_repository.find_by_id(lot_id)
    if not lot:
        raise NotFoundError("Lot not found.")
    crop = crop_repository.find_by_id(lot.crop_id) or Crop()
    horizon_days = int(horizon_days or settings.FORECAST_DEFAULT_HORIZON_DAYS)

    benchmark = market_service.benchmark_price(
        lot.crop_id, district=lot.district, target_unit=lot.unit
    )

    options = []
    options.extend(matching_service.buyer_options_for_lot(lot, limit=30))
    options.extend(_offer_options(lot))
    if include_markets:
        options.extend(_market_options(lot, crop))

    lot_inputs = {
        "quantity": float(lot.quantity or 0),
        "grade": lot.grade,
        "moisture_percent": lot.moisture_percent,
    }
    ranked = evaluate_options(
        lot_inputs,
        options,
        settings.matching_weights(),
        benchmark_price=benchmark.get("price"),
        max_distance_km=settings.MAX_MATCH_DISTANCE_KM,
    )[:limit]

    best = ranked[0] if ranked else None
    runner_up = ranked[1] if len(ranked) > 1 else None

    forecast = forecast_service.forecast_for(
        lot.crop_id,
        market_id=_reference_market_id(lot),
        horizon_days=horizon_days,
        store=False,
    )
    storage = storage_service.storage_context(lot, days=horizon_days, crop=crop)
    window = sale_window_advice(
        forecast,
        best_net_price_per_unit=(best or {}).get("net_price_per_unit"),
        holding_cost_per_unit=storage["holding_cost_per_unit"],
        horizon_days=horizon_days,
        has_active_demand=any(o["option_type"] in ("BUYER", "OFFER") for o in options),
        is_perishable=bool(crop.is_perishable),
        shelf_life_days=crop.shelf_life_days,
        storage_available=storage["available"],
        gain_margin_percent=settings.SALE_WINDOW_GAIN_MARGIN_PERCENT,
    )

    payload = {
        "lot": lot.to_dict(),
        "crop": crop.to_dict(),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "benchmark": benchmark,
        "recommended_option": best,
        "why_this_recommendation": explain_recommendation(best, runner_up, unit=lot.unit),
        "sale_window": window,
        "comparison": compare_top_options(ranked),
        "options": ranked,
        "options_considered": len(options),
        "market_context": _market_context(lot, crop),
        "price_forecast": forecast,
        "storage": storage,
        "weights": {
            "configured": settings.matching_weights(),
            "applied": net_adjusted_weights(settings.matching_weights()),
            "note": (
                "Options here are ranked on net realization, which already has transport "
                "deducted. Half the distance weight is therefore moved to price so the "
                "same journey is not charged twice; the remainder stands for travel time "
                "and the practical difficulty of dealing with a distant buyer."
            ),
        },
        "disclaimer": (
            "Transport, storage and net realization figures are estimates produced by "
            "KisanLink's cost model, not quotations. Buyer verification reflects a "
            "platform review only."
        ),
    }
    if not ranked:
        payload["message"] = (
            "No selling opportunity could be priced for this lot yet. "
            "Publish the lot, or check that market price data has been loaded for this crop."
        )

    if store:
        payload["recommendation_id"] = _store(lot, best, window, ranked, payload)
    return payload


def _offer_options(lot):
    """
    Live offers already made on this lot, costed the same way as everything else.

    A farmer comparing a real offer against a mandi price needs both computed
    identically, or the comparison is meaningless.
    """
    options = []
    origin = matching_service.lot_location(lot)
    for row in offer_repository.live_offers_for_lot(lot.id):
        buyer = buyer_profile_repository.find_by_id(row["buyer_id"])
        destination = {
            "latitude": buyer.latitude if buyer else None,
            "longitude": buyer.longitude if buyer else None,
            "district": row.get("buyer_district"),
            "state": buyer.state if buyer else lot.state,
        }
        measurement = maps_service.distance_between(origin, destination)
        quantity = float(row.get("quantity") or lot.quantity or 0)
        price = convert_price(
            row.get("price_per_unit"), (row.get("unit") or lot.unit), lot.unit
        )

        farmer_pays_transport = (row.get("transport_borne_by") or "FARMER").upper() == "FARMER"
        transport_cost, transport_estimate = 0.0, None
        if farmer_pays_transport:
            transport_estimate = logistics_service.estimate_transport(
                quantity, lot.unit, measurement["distance_km"]
            )
            transport_cost = transport_estimate.get("estimated_cost") or 0.0

        options.append(
            {
                "option_type": "OFFER",
                "option_id": row["id"],
                "buyer_id": row["buyer_id"],
                "label": f"{row.get('business_name')} (live offer)",
                "sublabel": "Offer already received on this lot",
                "channel": row.get("buyer_type") or "OTHER",
                "price_per_unit": round(price, 2) if price is not None else None,
                "price_basis": "Price quoted in the buyer's offer.",
                "unit": lot.unit,
                "tradeable_quantity": round(min(quantity, float(lot.quantity or 0)), 2),
                "delivery_mode": row.get("delivery_mode"),
                "transport_borne_by": row.get("transport_borne_by"),
                "payment_terms_days": row.get("payment_terms_days"),
                "valid_until": str(row.get("valid_until"))[:10] if row.get("valid_until") else None,
                "verification_status": row.get("verification_status"),
                "costs": {"transport": transport_cost},
                "transport_estimate": transport_estimate,
                "distance": measurement,
                "match_inputs": {
                    "required_quantity": quantity,
                    # An offer is made against this lot as it stands, so the
                    # buyer has already accepted its grade.
                    "min_grade": lot.grade,
                    "distance_km": measurement["distance_km"],
                    "proximity": measurement["proximity"],
                    "verification_status": row.get("verification_status"),
                    "trust_score": row.get("trust_score"),
                    "on_time_payment_rate": buyer.on_time_payment_rate if buyer else None,
                    "completed_transactions": buyer.completed_transactions if buyer else 0,
                },
            }
        )
    return options


def _market_options(lot, crop):
    """
    Price up the nearby mandis.

    Mandi charges (commission and market fee) are deducted here. Leaving them
    out is the single most common way a headline mandi price misleads a farmer.
    """
    markets = market_service.nearby_markets(
        latitude=lot.latitude,
        longitude=lot.longitude,
        district=lot.district,
        state=lot.state,
        crop_id=lot.crop_id,
        limit=MARKET_OPTION_LIMIT,
        max_distance_km=settings.MAX_MATCH_DISTANCE_KM,
    )
    lowest_grade = (crop.grades or ["C"])[-1]

    options = []
    for market in markets:
        latest = market.get("latest_price")
        if not latest or latest.get("modal_price") is None:
            continue
        price = convert_price(
            latest["modal_price"], latest.get("price_unit") or "QUINTAL", lot.unit
        )
        quantity = float(lot.quantity or 0)
        gross = price * quantity

        transport = logistics_service.estimate_transport(
            quantity, lot.unit, market.get("distance_km")
        )
        commission = gross * (
            settings.MANDI_COMMISSION_PERCENT + settings.MANDI_MARKET_FEE_PERCENT
        ) / 100.0

        regulated = (market.get("market_type") or "").upper() in ("APMC", "ENAM")
        options.append(
            {
                "option_type": "MARKET",
                "option_id": market["id"],
                "label": f"{market['name']} Mandi",
                "sublabel": MARKET_TYPE_LABELS.get(
                    (market.get("market_type") or "OTHER").upper(), "Market"
                ),
                "channel": "MANDI",
                "price_per_unit": round(price, 2),
                "price_basis": (
                    f"Modal price reported on {str(latest.get('price_date'))[:10]} "
                    f"(source: {latest.get('source')})."
                ),
                "unit": lot.unit,
                "tradeable_quantity": round(quantity, 2),
                "delivery_mode": "DELIVERED_AT_MARKET",
                "transport_borne_by": "FARMER",
                "arrival_quantity": latest.get("arrival_quantity"),
                "price_date": str(latest.get("price_date"))[:10] if latest.get("price_date") else None,
                "source": latest.get("source"),
                "costs": {
                    "transport": transport.get("estimated_cost") or 0.0,
                    "commission": round(commission, 2),
                },
                "cost_note": (
                    f"Includes {settings.MANDI_COMMISSION_PERCENT}% commission and "
                    f"{settings.MANDI_MARKET_FEE_PERCENT}% market fee, "
                    "which the headline mandi price does not show."
                ),
                "transport_estimate": transport,
                "distance": {
                    "distance_km": market.get("distance_km"),
                    "method": market.get("method"),
                    "proximity": market.get("proximity"),
                },
                "match_inputs": {
                    # A mandi will take the whole lot and accepts any grade;
                    # the grade shows up in the price it fetches, not in
                    # acceptance.
                    "required_quantity": quantity,
                    "min_grade": lowest_grade,
                    "distance_km": market.get("distance_km"),
                    "proximity": market.get("proximity"),
                    "verification_status": "REGULATED_MARKET" if regulated else "PRIVATE_MARKET",
                    "trust_score": 75 if regulated else 55,
                },
            }
        )
    return options


def _reference_market_id(lot):
    """The nearest market that actually reports this crop, for forecasting."""
    markets = market_repository.markets_trading_crop(lot.crop_id, limit=20)
    if not markets:
        return None
    origin = matching_service.lot_location(lot)
    ranked = maps_service.nearest(origin, markets, limit=1)
    return ranked[0]["id"] if ranked else markets[0]["id"]


def _market_context(lot, crop):
    """The intelligence panel: spread across markets, plus arrivals."""
    overview = market_service.market_overview(
        lot.crop_id, district=lot.district, state=lot.state, limit=10
    )
    market_id = _reference_market_id(lot)
    if market_id:
        overview["arrivals"] = market_service.arrivals(market_id, lot.crop_id, days=30)["summary"]
        overview["reference_market_id"] = market_id
    overview["crop_is_perishable"] = bool(crop.is_perishable)
    overview["shelf_life_days"] = crop.shelf_life_days
    return overview


def _store(lot, best, window, ranked, payload):
    """Save a snapshot of what was advised, minus the bulky nested detail."""
    slim = {
        "comparison": payload["comparison"],
        "why_this_recommendation": payload["why_this_recommendation"],
        "sale_window": window,
        "benchmark": payload["benchmark"],
        "weights": payload["weights"],
        "options_considered": payload["options_considered"],
    }
    return recommendation_repository.insert(
        {
            "lot_id": lot.id,
            "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "recommended_option_type": (best or {}).get("option_type"),
            "recommended_option_id": (best or {}).get("option_id"),
            "recommended_label": (best or {}).get("label"),
            "estimated_net_realization": (best or {}).get("realization", {}).get("net_amount"),
            "sale_window": window.get("recommendation"),
            "sale_window_confidence": window.get("confidence"),
            "option_count": len(ranked),
            "payload_json": json.dumps(slim, default=str),
        }
    )


def latest_recommendation(lot_id):
    record = recommendation_repository.latest_for_lot(lot_id)
    if not record:
        raise NotFoundError(
            "No recommendation has been generated for this lot yet."
        )
    return record.to_dict()


def recommendation_history(lot_id, limit=10):
    return [record.to_dict() for record in recommendation_repository.history_for_lot(lot_id, limit)]


def sale_window_only(lot_id, horizon_days=None):
    """Just the timing answer, for a lighter dashboard widget."""
    result = recommend_for_lot(lot_id, horizon_days=horizon_days, limit=3, store=False)
    return {
        "lot_id": lot_id,
        "sale_window": result["sale_window"],
        "price_forecast": result["price_forecast"],
        "storage": {
            "available": result["storage"]["available"],
            "holding_cost_per_unit": result["storage"]["holding_cost_per_unit"],
            "nearest_facility": result["storage"]["nearest_facility"],
        },
        "best_option": result["recommended_option"],
    }
