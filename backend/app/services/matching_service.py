"""
Matching farmers to buyers, and buyers to farmers.

The scoring itself lives in ``ml/matching_model.py``. This module's job is to
assemble honest inputs for it: find the candidate pool, convert units so a
per-kg price is never compared against a per-quintal one, work out distance and
who pays for transport, and attach the buyer's trust signals.
"""
from app.config.settings import settings
from app.models.buyer_requirement import BUYER_PAYS_TRANSPORT
from app.repositories.buyer_repository import buyer_requirement_repository
from app.repositories.crop_repository import crop_repository
from app.repositories.lot_repository import lot_repository
from app.repositories.trust_repository import grievance_repository
from app.repositories.user_repository import buyer_profile_repository
from app.services import logistics_service, maps_service, market_service
from app.utils.responses import NotFoundError
from app.utils.units import convert_price, convert_quantity, is_convertible

#: Channel label shown to the farmer for each buyer type.
CHANNEL_LABELS = {
    "PROCESSOR": "Processor",
    "INSTITUTIONAL": "Institutional Buyer",
    "AGGREGATOR": "Aggregator",
    "TRADER": "Trader",
    "EXPORTER": "Exporter",
    "OTHER": "Buyer",
}


def lot_location(lot):
    return {
        "latitude": lot.latitude,
        "longitude": lot.longitude,
        "district": lot.district,
        "state": lot.state,
    }


def requirement_location(requirement_row):
    """Where the crop would have to go: the delivery point, not the office."""
    return {
        "latitude": requirement_row.get("latitude") or requirement_row.get("buyer_latitude"),
        "longitude": requirement_row.get("longitude") or requirement_row.get("buyer_longitude"),
        "district": requirement_row.get("delivery_district") or requirement_row.get("buyer_district"),
        "state": requirement_row.get("delivery_state"),
    }


def build_buyer_option(lot, requirement_row, origin=None, include_transport=True):
    """
    Turn one buyer requirement into a comparable selling opportunity.

    Returns ``None`` when the two sides cannot be compared at all - for example
    a lot measured in dozens against a demand priced per quintal - rather than
    guessing a conversion.
    """
    origin = origin or lot_location(lot)
    lot_unit = (lot.unit or "QUINTAL").upper()
    requirement_unit = (requirement_row.get("unit") or "QUINTAL").upper()

    if not (is_convertible(lot_unit) and is_convertible(requirement_unit)):
        if lot_unit != requirement_unit:
            return None

    price_min = requirement_row.get("price_min")
    price_max = requirement_row.get("price_max")
    indicative = None
    if price_min is not None and price_max is not None:
        indicative = (float(price_min) + float(price_max)) / 2.0
    elif price_max is not None:
        indicative = float(price_max)
    elif price_min is not None:
        indicative = float(price_min)

    price_in_lot_unit = (
        convert_price(indicative, requirement_unit, lot_unit) if indicative is not None else None
    )
    remaining = float(requirement_row.get("required_quantity") or 0) - float(
        requirement_row.get("fulfilled_quantity") or 0
    )
    remaining_in_lot_unit = convert_quantity(max(remaining, 0), requirement_unit, lot_unit)
    tradeable = min(float(lot.quantity or 0), remaining_in_lot_unit or 0)

    destination = requirement_location(requirement_row)
    measurement = maps_service.distance_between(origin, destination)

    # Delivery mode decides whose cost the transport is. A farm-gate buyer
    # collecting from the field leaves the farmer with nothing to pay.
    delivery_mode = requirement_row.get("delivery_mode") or "DELIVERED_AT_BUYER"
    buyer_collects = delivery_mode in BUYER_PAYS_TRANSPORT
    transport_cost, transport_estimate = 0.0, None
    if include_transport and not buyer_collects and tradeable > 0:
        transport_estimate = logistics_service.estimate_transport(
            tradeable, lot_unit, measurement["distance_km"]
        )
        transport_cost = transport_estimate.get("estimated_cost") or 0.0

    buyer_id = requirement_row.get("buyer_id")
    buyer = buyer_profile_repository.find_by_id(buyer_id) if buyer_id else None
    open_grievances = (
        grievance_repository.open_count_against(buyer.user_id) if buyer else 0
    )

    business_name = requirement_row.get("business_name") or "Buyer"
    buyer_type = requirement_row.get("buyer_type") or "OTHER"

    return {
        "option_type": "BUYER",
        "option_id": requirement_row.get("id"),
        "buyer_id": buyer_id,
        "requirement_id": requirement_row.get("id"),
        "label": business_name,
        "sublabel": CHANNEL_LABELS.get(buyer_type, "Buyer"),
        "channel": buyer_type,
        "price_per_unit": round(price_in_lot_unit, 2) if price_in_lot_unit is not None else None,
        "price_basis": (
            "Midpoint of the buyer's declared price range."
            if price_min is not None and price_max is not None
            else "Buyer's declared price."
        ),
        "unit": lot_unit,
        "tradeable_quantity": round(tradeable, 2),
        "delivery_mode": delivery_mode,
        "transport_borne_by": "BUYER" if buyer_collects else "FARMER",
        "payment_terms_days": requirement_row.get("payment_terms_days"),
        "valid_until": str(requirement_row.get("valid_until"))[:10]
        if requirement_row.get("valid_until")
        else None,
        "verification_status": requirement_row.get("verification_status"),
        "costs": {"transport": transport_cost},
        "transport_estimate": transport_estimate,
        "distance": measurement,
        "match_inputs": {
            "required_quantity": round(remaining_in_lot_unit or 0, 2),
            "min_grade": requirement_row.get("min_grade"),
            "max_moisture_percent": requirement_row.get("max_moisture_percent"),
            "distance_km": measurement["distance_km"],
            "proximity": measurement["proximity"],
            "verification_status": requirement_row.get("verification_status"),
            "trust_score": requirement_row.get("trust_score"),
            "on_time_payment_rate": buyer.on_time_payment_rate if buyer else None,
            "completed_transactions": buyer.completed_transactions if buyer else 0,
            "open_grievances": open_grievances,
        },
    }


def buyer_options_for_lot(lot, limit=25, include_transport=True):
    """Every live demand for this lot's crop, expressed as a comparable option."""
    import datetime as dt

    rows = buyer_requirement_repository.active_for_crop(
        lot.crop_id, today=dt.date.today().isoformat(), limit=limit
    )
    origin = lot_location(lot)
    options = []
    for row in rows:
        option = build_buyer_option(lot, row, origin=origin, include_transport=include_transport)
        if option and option["tradeable_quantity"] > 0:
            options.append(option)
    return options


def match_lot(lot_id, limit=10, weights=None):
    """
    Rank buyers for one lot.

    This is the answer to "who should I sell to?" - scored, explained, and
    always returning more than one option so the farmer keeps the choice.
    """
    from ml.matching_model import rank_matches, score_match

    lot = lot_repository.find_by_id(lot_id)
    if not lot:
        raise NotFoundError("Lot not found.")
    crop = crop_repository.find_by_id(lot.crop_id)

    benchmark = market_service.benchmark_price(
        lot.crop_id, district=lot.district, target_unit=lot.unit
    )
    weights = weights or settings.matching_weights()
    options = buyer_options_for_lot(lot, limit=max(limit * 3, 30))

    lot_inputs = {
        "quantity": float(lot.quantity or 0),
        "grade": lot.grade,
        "moisture_percent": lot.moisture_percent,
    }

    scored = []
    for option in options:
        candidate = dict(option["match_inputs"])
        candidate["price"] = option["price_per_unit"]
        result = score_match(
            lot_inputs,
            candidate,
            weights,
            max_distance_km=settings.MAX_MATCH_DISTANCE_KM,
            benchmark_price=benchmark.get("price"),
        )
        scored.append(
            {
                **{k: v for k, v in option.items() if k != "match_inputs"},
                "match_score": result["total_score"],
                "score_components": result["components"],
                "blockers": result["blockers"],
                "is_viable": result["is_viable"],
            }
        )

    ranked = rank_matches(scored, key="match_score", limit=limit)
    return {
        "lot": lot.to_dict(),
        "crop": crop.to_dict() if crop else None,
        "benchmark": benchmark,
        "weights": weights,
        "weights_note": (
            "Weights are configured in settings, not learned from data. "
            "They can be tuned without changing any code."
        ),
        "candidates_considered": len(options),
        "matches": ranked,
        "message": (
            "No active buyer demand matches this crop yet."
            if not ranked
            else f"{len(ranked)} buying opportunities compared."
        ),
    }


def match_requirement(requirement_id, limit=10, weights=None):
    """
    The mirror image: rank farmer lots for one buyer requirement.

    This is what lets a buyer aggregate consistent volume instead of chasing
    lots one at a time.
    """
    from ml.matching_model import rank_matches, score_match

    requirement_row = buyer_requirement_repository.detail(requirement_id)
    if not requirement_row:
        raise NotFoundError("Buyer requirement not found.")

    requirement_unit = (requirement_row.get("unit") or "QUINTAL").upper()
    destination = requirement_location(requirement_row)
    weights = weights or settings.matching_weights()
    benchmark = market_service.benchmark_price(
        requirement_row["crop_id"],
        district=requirement_row.get("delivery_district"),
        target_unit=requirement_unit,
    )

    remaining = float(requirement_row.get("required_quantity") or 0) - float(
        requirement_row.get("fulfilled_quantity") or 0
    )
    lots = lot_repository.open_lots_for_crop(requirement_row["crop_id"], limit=100)

    scored = []
    for lot_row in lots:
        lot_unit = (lot_row.get("unit") or "QUINTAL").upper()
        if not (is_convertible(lot_unit) and is_convertible(requirement_unit)):
            if lot_unit != requirement_unit:
                continue
        quantity_in_requirement_unit = convert_quantity(
            lot_row.get("quantity"), lot_unit, requirement_unit
        )
        origin = {
            "latitude": lot_row.get("latitude"),
            "longitude": lot_row.get("longitude"),
            "district": lot_row.get("district"),
            "state": lot_row.get("state"),
        }
        measurement = maps_service.distance_between(origin, destination)
        asking_price = lot_row.get("expected_price")
        asking_in_requirement_unit = (
            convert_price(asking_price, lot_unit, requirement_unit)
            if asking_price is not None
            else None
        )

        # Scored from the buyer's side: a LOWER asking price is better for them,
        # so the price component is inverted around the market benchmark.
        price_for_scoring = None
        if asking_in_requirement_unit is not None and benchmark.get("price"):
            price_for_scoring = 2 * float(benchmark["price"]) - asking_in_requirement_unit

        result = score_match(
            {
                "quantity": quantity_in_requirement_unit,
                "grade": lot_row.get("grade"),
                "moisture_percent": lot_row.get("moisture_percent"),
            },
            {
                "price": price_for_scoring,
                "required_quantity": max(remaining, 0),
                "min_grade": requirement_row.get("min_grade"),
                "max_moisture_percent": requirement_row.get("max_moisture_percent"),
                "distance_km": measurement["distance_km"],
                "proximity": measurement["proximity"],
                # The seller has no verification workflow of their own yet, so
                # this component is neutral rather than invented.
                "verification_status": "DOCUMENTS_SUBMITTED",
                "trust_score": 50,
            },
            weights,
            max_distance_km=settings.MAX_MATCH_DISTANCE_KM,
            benchmark_price=benchmark.get("price"),
        )
        scored.append(
            {
                "lot_id": lot_row["id"],
                "lot_code": lot_row.get("lot_code"),
                "seller_name": lot_row.get("seller_name"),
                "seller_type": lot_row.get("seller_type"),
                "district": lot_row.get("district"),
                "village": lot_row.get("village"),
                "crop_name": lot_row.get("crop_name"),
                "grade": lot_row.get("grade"),
                "quantity": lot_row.get("quantity"),
                "unit": lot_unit,
                "quantity_in_requirement_unit": round(quantity_in_requirement_unit or 0, 2),
                "expected_price": asking_price,
                "expected_price_in_requirement_unit": round(asking_in_requirement_unit, 2)
                if asking_in_requirement_unit is not None
                else None,
                "available_from": str(lot_row.get("available_from"))[:10]
                if lot_row.get("available_from")
                else None,
                "distance": measurement,
                "match_score": result["total_score"],
                "score_components": result["components"],
                "blockers": result["blockers"],
                "is_viable": result["is_viable"],
            }
        )

    ranked = rank_matches(scored, key="match_score", limit=limit)
    total_available = sum(
        item["quantity_in_requirement_unit"] for item in ranked if item["is_viable"]
    )
    return {
        "requirement": requirement_row,
        "benchmark": benchmark,
        "weights": weights,
        "lots_considered": len(scored),
        "matches": ranked,
        "aggregation": {
            "remaining_quantity": round(max(remaining, 0), 2),
            "matched_quantity_available": round(total_available, 2),
            "fully_coverable": total_available >= max(remaining, 0) > 0,
            "lots_needed": _lots_needed(ranked, max(remaining, 0)),
            "note": (
                "Several lots can be combined to fill this requirement."
                if total_available >= max(remaining, 0) > 0
                else "Available matching supply does not yet cover this requirement."
            ),
        },
    }


def _lots_needed(ranked, remaining):
    """How many of the top lots it would take to fill the requirement."""
    if remaining <= 0:
        return 0
    running, count = 0.0, 0
    for item in ranked:
        if not item.get("is_viable"):
            continue
        running += item["quantity_in_requirement_unit"]
        count += 1
        if running >= remaining:
            return count
    return None
