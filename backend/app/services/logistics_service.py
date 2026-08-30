"""
Transport estimation and transport-request tracking.

There is no live freight API behind this. Costs come from a transparent model
whose parameters sit in ``settings.py``, and every figure is returned labelled
as an estimate with the assumptions attached.
"""
import datetime as dt

from app.config.settings import settings
from app.models.logistics_request import STATUS_FLOW, STATUSES
from app.repositories.logistics_repository import logistics_repository
from app.repositories.lot_repository import lot_repository
from app.repositories.transaction_repository import transaction_repository
from app.services import maps_service
from app.utils.responses import ForbiddenError, NotFoundError, ValidationError
from app.utils.units import to_tonnes

#: Vehicle bands by payload. Picked by capacity, cheapest adequate first.
VEHICLE_BANDS = (
    ("TRACTOR_TROLLEY", 3.0),
    ("TEMPO", 1.5),
    ("PICKUP", 2.5),
    ("TRUCK_9T", 9.0),
    ("TRUCK_16T", 16.0),
)


def choose_vehicle(tonnes):
    """Smallest vehicle that can carry the load in one trip, else the largest."""
    for name, capacity in sorted(VEHICLE_BANDS, key=lambda band: band[1]):
        if tonnes <= capacity:
            return name, capacity
    return "TRUCK_16T", 16.0


def estimate_transport(quantity, unit, distance_km):
    """
    Estimate what it costs to move a lot a given distance.

    Model: a base fare, plus a per-km per-tonne rate, plus loading/unloading,
    with a minimum charge. Returns the assumptions alongside the number so the
    farmer can see it is an estimate and not a quotation.
    """
    if distance_km is None:
        return {
            "available": False,
            "estimated_cost": None,
            "reason": (
                "Distance could not be determined, so transport cost was not estimated."
            ),
        }

    tonnes = to_tonnes(quantity, unit)
    distance_km = float(distance_km)
    vehicle, capacity = choose_vehicle(tonnes)
    trips = max(1, int((tonnes + capacity - 0.001) // capacity))

    variable = settings.TRANSPORT_RATE_PER_KM_PER_TONNE * distance_km * tonnes
    loading = settings.LOADING_COST_PER_TONNE * tonnes
    base = settings.TRANSPORT_BASE_FARE * trips
    total = max(base + variable + loading, settings.TRANSPORT_MIN_CHARGE)

    per_unit = total / float(quantity) if quantity else None
    return {
        "available": True,
        "estimated_cost": round(total, 2),
        "cost_per_unit": round(per_unit, 2) if per_unit is not None else None,
        "unit": unit,
        "distance_km": round(distance_km, 1),
        "tonnes": round(tonnes, 3),
        "vehicle_type": vehicle,
        "trips": trips,
        "is_estimate": True,
        "breakdown": {
            "base_fare": round(base, 2),
            "distance_component": round(variable, 2),
            "loading_unloading": round(loading, 2),
            "minimum_charge_applied": total == settings.TRANSPORT_MIN_CHARGE,
        },
        "assumptions": (
            f"Rs {settings.TRANSPORT_BASE_FARE:,.0f} base fare per trip, "
            f"Rs {settings.TRANSPORT_RATE_PER_KM_PER_TONNE:,.2f} per km per tonne, "
            f"Rs {settings.LOADING_COST_PER_TONNE:,.0f} per tonne loading/unloading, "
            f"minimum Rs {settings.TRANSPORT_MIN_CHARGE:,.0f}. "
            "This is a planning estimate, not a transporter's quotation."
        ),
    }


def estimate_between(origin, destination, quantity, unit):
    """Distance plus cost in one call - what the recommendation engine needs."""
    measurement = maps_service.distance_between(origin, destination)
    estimate = estimate_transport(quantity, unit, measurement["distance_km"])
    estimate["distance"] = measurement
    return estimate


def create_request(user, data):
    """Raise a transport request against a transaction or a lot."""
    transaction_id = data.get("transaction_id")
    lot_id = data.get("lot_id")
    if not transaction_id and not lot_id:
        raise ValidationError("Provide either 'transaction_id' or 'lot_id'.")

    if transaction_id:
        transaction = transaction_repository.find_by_id(transaction_id)
        if not transaction:
            raise NotFoundError("Transaction not found.")
        _assert_party(user, transaction)
        lot_id = lot_id or transaction.lot_id
        data.setdefault("quantity", float(transaction.quantity))
        data.setdefault("unit", transaction.unit)

    if lot_id:
        lot = lot_repository.find_by_id(lot_id)
        if not lot:
            raise NotFoundError("Lot not found.")
        data.setdefault("pickup_district", lot.district)
        data.setdefault("pickup_latitude", lot.latitude)
        data.setdefault("pickup_longitude", lot.longitude)
        data.setdefault("quantity", float(lot.quantity))
        data.setdefault("unit", lot.unit)

    measurement = maps_service.distance_between(
        {
            "latitude": data.get("pickup_latitude"),
            "longitude": data.get("pickup_longitude"),
            "district": data.get("pickup_district"),
        },
        {
            "latitude": data.get("drop_latitude"),
            "longitude": data.get("drop_longitude"),
            "district": data.get("drop_district"),
        },
    )
    estimate = estimate_transport(
        data.get("quantity"), data.get("unit", "QUINTAL"), measurement["distance_km"]
    )

    payload = dict(data)
    payload.update(
        {
            "lot_id": lot_id,
            "transaction_id": transaction_id,
            "requested_by_user_id": user.id,
            "distance_km": measurement["distance_km"],
            "estimated_cost": estimate.get("estimated_cost"),
            "vehicle_type": data.get("vehicle_type") or estimate.get("vehicle_type"),
            "status": "REQUESTED",
        }
    )
    request_id = logistics_repository.insert(payload)
    return logistics_repository.detail(request_id)


def _assert_party(user, transaction):
    from app.repositories.user_repository import buyer_profile_repository

    if user.role == "ADMIN" or transaction.seller_user_id == user.id:
        return
    buyer = buyer_profile_repository.find_by_user_id(user.id)
    if buyer and buyer.id == transaction.buyer_id:
        return
    raise ForbiddenError("You are not a party to this transaction.")


def get_request(request_id):
    request = logistics_repository.detail(request_id)
    if not request:
        raise NotFoundError("Logistics request not found.")
    return request


def list_requests(user=None, **filters):
    if user is not None and user.role != "ADMIN":
        filters.setdefault("requested_by_user_id", user.id)
    return logistics_repository.search(**filters)


def update_status(request_id, new_status, user, notes=None, actual_cost=None):
    """Move a transport request along its allowed status path."""
    request = logistics_repository.find_by_id(request_id)
    if not request:
        raise NotFoundError("Logistics request not found.")
    new_status = new_status.upper()
    if new_status not in STATUSES:
        raise ValidationError(f"'status' must be one of: {', '.join(STATUSES)}.")
    allowed = STATUS_FLOW.get(request.status, ())
    if new_status not in allowed:
        raise ValidationError(
            f"A '{request.status}' request cannot move to '{new_status}'. "
            f"Allowed next steps: {', '.join(allowed) if allowed else 'none'}."
        )
    if request.requested_by_user_id != user.id and user.role != "ADMIN":
        raise ForbiddenError("Only the requester or an administrator can update this request.")

    payload = {"status": new_status}
    if notes:
        payload["notes"] = notes
    if actual_cost is not None:
        payload["actual_cost"] = actual_cost
    if new_status == "DELIVERED":
        payload["scheduled_date"] = request.scheduled_date or dt.date.today().isoformat()
    logistics_repository.update(request_id, payload)
    return logistics_repository.detail(request_id)


def assign_provider(request_id, provider_name, provider_phone, user, scheduled_date=None):
    request = logistics_repository.find_by_id(request_id)
    if not request:
        raise NotFoundError("Logistics request not found.")
    if request.requested_by_user_id != user.id and user.role != "ADMIN":
        raise ForbiddenError("Only the requester or an administrator can assign a provider.")
    logistics_repository.update(
        request_id,
        {
            "provider_name": provider_name,
            "provider_phone": provider_phone,
            "scheduled_date": scheduled_date,
            "status": "ASSIGNED" if request.status == "REQUESTED" else request.status,
        },
    )
    return logistics_repository.detail(request_id)
