"""
Storage options and the cost of holding a crop.

Storage matters here for one specific reason: a farmer with nowhere to keep the
crop has to accept whatever is offered on harvest day. Showing what holding
would cost - and whether a facility is even available - turns "sell now" from a
constraint into a decision.
"""
from app.config.settings import settings
from app.repositories.storage_repository import storage_repository
from app.services import maps_service
from app.utils.responses import NotFoundError
from app.utils.units import to_tonnes


def list_facilities(district=None, state=None, facility_type=None, cold_only=False,
                    min_available_tonnes=None, page=1, page_size=20, order_by=None):
    facilities, total = storage_repository.search(
        district=district,
        state=state,
        facility_type=facility_type,
        cold_only=cold_only,
        min_available_tonnes=min_available_tonnes,
        page=page,
        page_size=page_size,
        order_by=order_by,
    )
    return [facility.to_dict() for facility in facilities], total


def get_facility(facility_id):
    facility = storage_repository.find_by_id(facility_id)
    if not facility:
        raise NotFoundError("Storage facility not found.")
    return facility


def create_facility(data):
    facility_id = storage_repository.insert(data)
    return storage_repository.find_by_id(facility_id).to_dict()


def nearby_facilities(latitude=None, longitude=None, district=None, state=None,
                      required_tonnes=None, cold_storage=False, limit=10,
                      max_distance_km=150):
    """Storage near the farm that can actually take the quantity."""
    origin = {
        "latitude": latitude,
        "longitude": longitude,
        "district": district,
        "state": state,
    }
    candidates = [facility.to_dict() for facility in storage_repository.with_coordinates(state)]
    if not candidates:
        facilities, _ = storage_repository.search(district=district, state=state, page_size=limit)
        candidates = [facility.to_dict() for facility in facilities]

    if cold_storage:
        candidates = [c for c in candidates if c.get("has_cold_storage")]
    if required_tonnes:
        candidates = [
            c
            for c in candidates
            if c.get("available_capacity_tonnes") is None
            or float(c["available_capacity_tonnes"]) >= float(required_tonnes)
        ]
    return maps_service.nearest(origin, candidates, limit=limit, max_distance_km=max_distance_km)


def estimate_storage_cost(quantity, unit, days, facility=None, crop_is_perishable=False):
    """
    What it costs to hold this quantity for a number of days.

    Two components: the storage charge itself, and an allowance for physical
    loss while stored. Ignoring the loss would make waiting look cheaper than
    it is, which is exactly the kind of error that costs a farmer money.
    """
    days = max(0, int(days or 0))
    tonnes = to_tonnes(quantity, unit)

    if facility is not None:
        rate = facility.cost_per_tonne_per_day
        source = f"{facility.name} ({facility.facility_type.replace('_', ' ').title()})"
    else:
        rate = None
        source = "platform default assumption"
    if rate is None:
        rate = settings.DEFAULT_STORAGE_COST_PER_TONNE_PER_DAY

    storage_charge = float(rate) * tonnes * days
    loss_fraction = (settings.STORAGE_LOSS_PERCENT_PER_DAY / 100.0) * days
    if crop_is_perishable:
        # Perishables deteriorate faster; doubling the allowance is a blunt but
        # honest way to stop the model recommending that they be held.
        loss_fraction *= 2

    return {
        "days": days,
        "tonnes": round(tonnes, 3),
        "rate_per_tonne_per_day": round(float(rate), 2),
        "storage_charge": round(storage_charge, 2),
        "expected_loss_percent": round(loss_fraction * 100, 2),
        "cost_source": source,
        "is_estimate": True,
        "note": (
            f"Estimated at Rs {float(rate):,.2f} per tonne per day from {source}, "
            f"plus an allowance of {loss_fraction * 100:.1f}% for storage loss over {days} days."
        ),
    }


def holding_cost_per_unit(quantity, unit, days, price_per_unit, facility=None,
                          crop_is_perishable=False):
    """
    Total cost of waiting, expressed per unit so it can be set against a
    forecast price gain directly.
    """
    estimate = estimate_storage_cost(quantity, unit, days, facility, crop_is_perishable)
    quantity = float(quantity or 0)
    if quantity <= 0:
        return 0.0, estimate
    charge_per_unit = estimate["storage_charge"] / quantity
    loss_per_unit = float(price_per_unit or 0) * estimate["expected_loss_percent"] / 100.0
    estimate["charge_per_unit"] = round(charge_per_unit, 2)
    estimate["loss_value_per_unit"] = round(loss_per_unit, 2)
    estimate["total_per_unit"] = round(charge_per_unit + loss_per_unit, 2)
    return estimate["total_per_unit"], estimate


def storage_context(lot, days=7, crop=None):
    """
    The storage panel for a lot: is there anywhere to put it, and at what cost?

    Returns ``available: False`` when no facility is on file, which the sale
    window logic treats as a reason not to advise waiting.
    """
    facilities = nearby_facilities(
        latitude=lot.latitude,
        longitude=lot.longitude,
        district=lot.district,
        state=lot.state,
        required_tonnes=to_tonnes(lot.quantity, lot.unit),
        cold_storage=bool(crop and crop.is_perishable),
        limit=5,
    )
    nearest_facility = None
    if facilities:
        nearest_facility = storage_repository.find_by_id(facilities[0]["id"])

    per_unit, estimate = holding_cost_per_unit(
        lot.quantity,
        lot.unit,
        days,
        lot.expected_price,
        facility=nearest_facility,
        crop_is_perishable=bool(crop and crop.is_perishable),
    )
    return {
        "available": bool(facilities),
        "facilities": facilities,
        "nearest_facility": facilities[0] if facilities else None,
        "holding_cost_per_unit": per_unit,
        "estimate": estimate,
        "note": (
            "No storage facility is on record near this lot, so holding the crop would "
            "mean keeping it on farm."
            if not facilities
            else estimate["note"]
        ),
    }
