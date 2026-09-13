"""
Transport estimation and transport-request tracking.

There is no live freight API behind this. Costs come from a transparent model
whose parameters sit in ``settings.py``, and every figure is returned labelled
as an estimate with the assumptions attached.
"""
import datetime as dt

from app.config.settings import settings
from app.models.logistics_request import STATUS_FLOW, STATUSES
from app.models.logistics_incident import (
    ACCIDENT,
    VEHICLE_BREAKDOWN,
    VEHICLE_UNAVAILABLE,
    INCIDENT_STATUSES,
    INCIDENT_TYPES,
)
from app.models.user import ADMIN, TRANSPORTER
from app.repositories.logistics_repository import logistics_repository
from app.repositories.lot_repository import lot_repository
from app.repositories.transaction_repository import transaction_repository
from app.repositories.transport_repository import (
    transporter_repository,
    vehicle_repository,
)
from app.repositories.incident_repository import incident_repository
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


ROUTE_NOT_STARTED = "NOT_STARTED"
ROUTE_IN_PROGRESS = "IN_PROGRESS"
ROUTE_COMPLETED = "COMPLETED"

ROUTE_STATUSES = (
    ROUTE_NOT_STARTED,
    ROUTE_IN_PROGRESS,
    ROUTE_COMPLETED,
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
                "Distance could not be determined, so transport cost "
                "was not estimated."
            ),
        }

    tonnes = to_tonnes(quantity, unit)
    distance_km = float(distance_km)

    vehicle, capacity = choose_vehicle(tonnes)
    trips = max(
        1,
        int((tonnes + capacity - 0.001) // capacity),
    )

    variable = (
        settings.TRANSPORT_RATE_PER_KM_PER_TONNE
        * distance_km
        * tonnes
    )

    loading = settings.LOADING_COST_PER_TONNE * tonnes
    base = settings.TRANSPORT_BASE_FARE * trips
    total = max(
        base + variable + loading,
        settings.TRANSPORT_MIN_CHARGE,
    )

    per_unit = total / float(quantity) if quantity else None

    return {
        "available": True,
        "estimated_cost": round(total, 2),
        "cost_per_unit": (
            round(per_unit, 2)
            if per_unit is not None
            else None
        ),
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
            "minimum_charge_applied": (
                total == settings.TRANSPORT_MIN_CHARGE
            ),
        },
        "assumptions": (
            f"Rs {settings.TRANSPORT_BASE_FARE:,.0f} base fare per trip, "
            f"Rs {settings.TRANSPORT_RATE_PER_KM_PER_TONNE:,.2f} "
            "per km per tonne, "
            f"Rs {settings.LOADING_COST_PER_TONNE:,.0f} "
            "per tonne loading/unloading, "
            f"minimum Rs {settings.TRANSPORT_MIN_CHARGE:,.0f}. "
            "This is a planning estimate, not a transporter's quotation."
        ),
    }


def estimate_between(origin, destination, quantity, unit):
    """Distance plus cost in one call - what the recommendation engine needs."""
    measurement = maps_service.distance_between(
        origin,
        destination,
    )

    estimate = estimate_transport(
        quantity,
        unit,
        measurement["distance_km"],
    )

    estimate["distance"] = measurement

    return estimate


def calculate_eta(distance_km):
    """Return a simple planning ETA based on an assumed average speed."""
    if distance_km is None:
        return None

    distance_km = float(distance_km)

    # Planning assumption, not live traffic data.
    average_speed_kmph = 30.0

    return round(
        (distance_km / average_speed_kmph) * 60,
        2,
    )


def create_request(user, data):
    """Raise a transport request against a transaction or a lot."""
    transaction_id = data.get("transaction_id")
    lot_id = data.get("lot_id")

    if not transaction_id and not lot_id:
        raise ValidationError(
            "Provide either 'transaction_id' or 'lot_id'."
        )

    if transaction_id:
        transaction = transaction_repository.find_by_id(
            transaction_id
        )

        if not transaction:
            raise NotFoundError("Transaction not found.")

        _assert_party(user, transaction)

        lot_id = lot_id or transaction.lot_id

        data.setdefault(
            "quantity",
            float(transaction.quantity),
        )

        data.setdefault(
            "unit",
            transaction.unit,
        )

    if lot_id:
        lot = lot_repository.find_by_id(lot_id)

        if not lot:
            raise NotFoundError("Lot not found.")

        data.setdefault(
            "pickup_district",
            lot.district,
        )

        data.setdefault(
            "pickup_latitude",
            lot.latitude,
        )

        data.setdefault(
            "pickup_longitude",
            lot.longitude,
        )

        data.setdefault(
            "quantity",
            float(lot.quantity),
        )

        data.setdefault(
            "unit",
            lot.unit,
        )

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
        data.get("quantity"),
        data.get("unit", "QUINTAL"),
        measurement["distance_km"],
    )

    payload = dict(data)

    payload.update(
        {
            "lot_id": lot_id,
            "transaction_id": transaction_id,
            "requested_by_user_id": user.id,
            "distance_km": measurement["distance_km"],
            "estimated_cost": estimate.get("estimated_cost"),
            "vehicle_type": (
                data.get("vehicle_type")
                or estimate.get("vehicle_type")
            ),
            "eta_minutes": calculate_eta(
                measurement["distance_km"]
            ),
            "route_status": ROUTE_NOT_STARTED,
            "route_progress_percent": 0,
            "incident_status": "NONE",
            "status": "REQUESTED",
        }
    )

    request_id = logistics_repository.insert(payload)

    return logistics_repository.detail(request_id)


def _assert_party(user, transaction):
    from app.repositories.user_repository import buyer_profile_repository

    if (
        user.role == ADMIN
        or transaction.seller_user_id == user.id
    ):
        return

    buyer = buyer_profile_repository.find_by_user_id(user.id)

    if buyer and buyer.id == transaction.buyer_id:
        return

    raise ForbiddenError(
        "You are not a party to this transaction."
    )


def get_request(request_id):
    request = logistics_repository.detail(request_id)

    if not request:
        raise NotFoundError(
            "Logistics request not found."
        )

    return request


def list_requests(user=None, **filters):
    if user is not None and user.role != ADMIN:
        filters.setdefault(
            "requested_by_user_id",
            user.id,
        )

    return logistics_repository.search(**filters)


def update_status(
    request_id,
    new_status,
    user,
    notes=None,
    actual_cost=None,
):
    """Move a transport request along its allowed status path."""
    request = logistics_repository.find_by_id(request_id)

    if not request:
        raise NotFoundError(
            "Logistics request not found."
        )

    new_status = new_status.upper()

    if new_status not in STATUSES:
        raise ValidationError(
            f"'status' must be one of: {', '.join(STATUSES)}."
        )

    allowed = STATUS_FLOW.get(
        request.status,
        (),
    )

    if new_status not in allowed:
        raise ValidationError(
            f"A '{request.status}' request cannot move to "
            f"'{new_status}'. "
            f"Allowed next steps: "
            f"{', '.join(allowed) if allowed else 'none'}."
        )

    is_requester = (
        request.requested_by_user_id == user.id
    )

    is_admin = user.role == ADMIN

    assigned_transporter = None

    if user.role == TRANSPORTER:
        assigned_transporter = (
            transporter_repository.find_by_user_id(user.id)
        )

    is_assigned_transporter = (
        assigned_transporter is not None
        and request.transporter_id == assigned_transporter.id
    )

    if not (
        is_requester
        or is_admin
        or is_assigned_transporter
    ):
        raise ForbiddenError(
            "Only the requester, assigned transporter, or "
            "administrator can update this request."
        )

    # Keep the related transaction status synchronized with logistics.
    transaction = None
    transaction_status = None

    if request.transaction_id:
        transaction = transaction_repository.find_by_id(
            request.transaction_id
        )

        if not transaction:
            raise NotFoundError(
                "Related transaction not found."
            )

        transaction_status_map = {
            "IN_TRANSIT": "IN_TRANSIT",
            "DELIVERED": "DELIVERED",
            "CANCELLED": "CANCELLED",
        }

        transaction_status = transaction_status_map.get(
            new_status
        )

        if transaction_status:
            from app.services import transaction_service

            transaction_service.update_status(
                user,
                request.transaction_id,
                transaction_status,
                notes
                or f"Logistics request moved to {new_status}.",
            )

    payload = {
        "status": new_status,
    }

    route_updates = {
        "ASSIGNED": {
            "route_status": ROUTE_NOT_STARTED,
            "route_progress_percent": 0,
        },
        "IN_TRANSIT": {
            "route_status": ROUTE_IN_PROGRESS,
            "route_progress_percent": 50,
        },
        "DELIVERED": {
            "route_status": ROUTE_COMPLETED,
            "route_progress_percent": 100,
        },
    }

    if new_status in route_updates:
        payload.update(
            route_updates[new_status]
        )

    if notes:
        payload["notes"] = notes

    if actual_cost is not None:
        payload["actual_cost"] = actual_cost

    if new_status == "DELIVERED":
        payload["scheduled_date"] = (
            request.scheduled_date
            or dt.date.today().isoformat()
        )

    logistics_repository.update(
        request_id,
        payload,
    )
    # Release the assigned vehicle after the trip ends.
    if new_status in ("DELIVERED", "CANCELLED") and request.vehicle_id:
        if request.vehicle_id:
            vehicle_repository.update(
                request.vehicle_id,
                {
                    "is_available": 1,
                },
            )

        if request.transporter_id:
            transporter_repository.update(
                request.transporter_id,
                {
                    "is_available": 1,
                },
            )

    return logistics_repository.detail(request_id)


def assign_provider(
    request_id,
    provider_name,
    provider_phone,
    user,
    scheduled_date=None,
):
    request = logistics_repository.find_by_id(request_id)

    if not request:
        raise NotFoundError(
            "Logistics request not found."
        )

    if (
        request.requested_by_user_id != user.id
        and user.role != ADMIN
    ):
        raise ForbiddenError(
            "Only the requester or an administrator "
            "can assign a provider."
        )

    logistics_repository.update(
        request_id,
        {
            "provider_name": provider_name,
            "provider_phone": provider_phone,
            "scheduled_date": scheduled_date,
            "status": (
                "ASSIGNED"
                if request.status == "REQUESTED"
                else request.status
            ),
        },
    )

    return logistics_repository.detail(request_id)


def register_transporter(user, data):
    """Create or update the transporter profile for a transporter user."""
    if user.role not in (TRANSPORTER, ADMIN):
        raise ForbiddenError(
            "Only a transporter or administrator can "
            "create a transporter profile."
        )

    user_id = data.get("user_id") or user.id

    existing = transporter_repository.find_by_user_id(
        user_id
    )

    payload = {
        "business_name": (
            data.get("business_name")
            or user.name
        ),
        "phone": (
            data.get("phone")
            or user.phone
        ),
        "district": data.get("district"),
        "state": data.get(
            "state",
            "Maharashtra",
        ),
    }

    if existing:
        transporter_repository.update(
            existing.id,
            payload,
        )
        transporter_id = existing.id

    else:
        payload["user_id"] = user_id

        transporter_id = transporter_repository.insert(
            payload
        )

    return transporter_repository.find_by_id(
        transporter_id
    )


def list_transporters(
    district=None,
    available_only=True,
    verification_status=None,
    query=None,
    page=1,
    page_size=20,
):
    """List transporters for selection or backup assignment."""
    rows, total = transporter_repository.search(
        district=district,
        available_only=available_only,
        verification_status=verification_status,
        query=query,
        page=page,
        page_size=page_size,
    )

    return {
        "items": [
            row.to_dict()
            for row in rows
        ],
        "total": total,
        "page": int(page),
        "page_size": int(page_size),
    }


def register_vehicle(user, data):
    """Register a vehicle against a transporter profile."""
    transporter_id = data.get("transporter_id")

    transporter = transporter_repository.find_by_id(
        transporter_id
    )

    if not transporter:
        raise NotFoundError(
            "Transporter not found."
        )

    if user.role != ADMIN:
        own_transporter = (
            transporter_repository.find_by_user_id(
                user.id
            )
        )

        if (
            not own_transporter
            or own_transporter.id != transporter_id
        ):
            raise ForbiddenError(
                "You can only register vehicles for your "
                "own transporter profile."
            )

    vehicle_id = vehicle_repository.insert(
        {
            "transporter_id": transporter_id,
            "vehicle_type": data["vehicle_type"],
            "vehicle_number": data["vehicle_number"],
            "capacity_tonnes": data["capacity_tonnes"],
            "service_area": data.get("service_area"),
            "rate_per_km": data.get("rate_per_km"),
        }
    )

    return vehicle_repository.detail_with_transporter(
        vehicle_id
    )


def list_available_vehicles(
    vehicle_type=None,
    min_capacity=None,
    transporter_id=None,
):
    """Return vehicles currently available for assignment."""
    vehicles = vehicle_repository.search_available(
        vehicle_type=vehicle_type,
        min_capacity=min_capacity,
        transporter_id=transporter_id,
    )

    return [
        vehicle.to_dict()
        for vehicle in vehicles
    ]


def assign_transporter(
    request_id,
    transporter_id,
    vehicle_id,
    user,
):
    """Assign a transporter and vehicle to a logistics request."""
    request = logistics_repository.find_by_id(
        request_id
    )

    if not request:
        raise NotFoundError(
            "Logistics request not found."
        )

    if (
        user.role != ADMIN
        and request.requested_by_user_id != user.id
    ):
        raise ForbiddenError(
            "Only the requester or an administrator "
            "can assign a transporter."
        )

    transporter = transporter_repository.find_by_id(
        transporter_id
    )

    if not transporter:
        raise NotFoundError(
            "Transporter not found."
        )

    if not transporter.is_available:
        raise ValidationError(
            "Transporter is not available."
        )

    vehicle = vehicle_repository.find_by_id(
        vehicle_id
    )

    if not vehicle:
        raise NotFoundError(
            "Vehicle not found."
        )

    if vehicle.transporter_id != transporter_id:
        raise ValidationError(
            "The selected vehicle does not belong "
            "to the selected transporter."
        )

    if not vehicle.is_available:
        raise ValidationError(
            "Vehicle is not available."
        )

    required_tonnes = to_tonnes(
        request.quantity,
        request.unit,
    )

    if vehicle.capacity_tonnes < required_tonnes:
        raise ValidationError(
            "Selected vehicle does not have enough "
            "capacity for this request."
        )

    transporter_repository.refresh_score(
        transporter_id
    )

    transporter = transporter_repository.find_by_id(
        transporter_id
    )

    logistics_repository.update(
        request_id,
        {
            "transporter_id": transporter_id,
            "vehicle_id": vehicle_id,
            "reliability_score": (
                transporter.reliability_score
            ),
            "status": (
                "ASSIGNED"
                if request.status == "REQUESTED"
                else request.status
            ),
            "route_status": ROUTE_NOT_STARTED,
            "route_progress_percent": 0,
        },
    )

    vehicle_repository.update(
        vehicle_id,
        {
            "is_available": 0,
        },
    )

    transporter_repository.update(
        transporter_id,
        {
            "is_available": 0,
        },
    )

    return logistics_repository.detail(
        request_id
    )


def get_backup_options(request_id):
    """Find available replacement transporters and vehicles."""
    request = logistics_repository.find_by_id(
        request_id
    )

    if not request:
        raise NotFoundError(
            "Logistics request not found."
        )

    required_tonnes = to_tonnes(
        request.quantity,
        request.unit,
    )

    options = logistics_repository.backup_options(
        request_id,
        min_capacity=required_tonnes,
    )

    return options


def reassign_transport(
    request_id,
    transporter_id,
    vehicle_id,
    user,
):
    """Replace the current transporter/vehicle with a backup option."""
    request = logistics_repository.find_by_id(
        request_id
    )

    if not request:
        raise NotFoundError(
            "Logistics request not found."
        )

    if (
        user.role != ADMIN
        and request.requested_by_user_id != user.id
    ):
        raise ForbiddenError(
            "Only the requester or an administrator "
            "can reassign transport."
        )

    old_transporter_id = request.transporter_id
    old_vehicle_id = request.vehicle_id

    result = assign_transporter(
        request_id,
        transporter_id,
        vehicle_id,
        user,
    )

    if (
        old_vehicle_id
        and old_vehicle_id != vehicle_id
    ):
        vehicle_repository.update(
            old_vehicle_id,
            {
                "is_available": 1,
            },
        )

    if (
        old_transporter_id
        and old_transporter_id != transporter_id
    ):
        transporter_repository.update(
            old_transporter_id,
            {
                "is_available": 1,
            },
        )

    return result


def update_eta_progress(
    request_id,
    eta_minutes,
    route_status=None,
    route_progress_percent=None,
    user=None,
):
    """Update planning ETA and route progress."""
    request = logistics_repository.find_by_id(
        request_id
    )

    if not request:
        raise NotFoundError(
            "Logistics request not found."
        )

    is_requester = (
        request.requested_by_user_id == user.id
    )

    is_admin = user.role == ADMIN

    assigned_transporter = None

    if user.role == TRANSPORTER:
        assigned_transporter = (
            transporter_repository.find_by_user_id(
                user.id
            )
        )

    is_assigned_transporter = (
        assigned_transporter is not None
        and request.transporter_id
        == assigned_transporter.id
    )

    allowed = (
        is_admin
        or is_requester
        or is_assigned_transporter
    )

    if not allowed:
        raise ForbiddenError(
            "You are not allowed to update "
            "this logistics route."
        )

    if (
        route_status
        and route_status not in ROUTE_STATUSES
    ):
        raise ValidationError(
            f"'route_status' must be one of: "
            f"{', '.join(ROUTE_STATUSES)}."
        )

    payload = {
        "eta_minutes": eta_minutes,
    }

    if route_status:
        payload["route_status"] = route_status

    if route_progress_percent is not None:
        payload["route_progress_percent"] = (
            route_progress_percent
        )

    logistics_repository.update(
        request_id,
        payload,
    )

    return logistics_repository.detail(
        request_id
    )


def report_incident(
    request_id,
    incident_type,
    description,
    user,
):
    """Report a basic logistics incident."""
    request = logistics_repository.find_by_id(
        request_id
    )

    if not request:
        raise NotFoundError(
            "Logistics request not found."
        )

    is_requester = (
        request.requested_by_user_id == user.id
    )

    is_admin = user.role == ADMIN

    assigned_transporter = None

    if user.role == TRANSPORTER:
        assigned_transporter = (
            transporter_repository.find_by_user_id(
                user.id
            )
        )

    is_assigned_transporter = (
        assigned_transporter is not None
        and request.transporter_id
        == assigned_transporter.id
    )

    allowed = (
        is_admin
        or is_requester
        or is_assigned_transporter
    )

    if not allowed:
        raise ForbiddenError(
            "You are not allowed to report an incident "
            "for this request."
        )

    incident_type = incident_type.upper()

    if incident_type not in INCIDENT_TYPES:
        raise ValidationError(
            f"'incident_type' must be one of: "
            f"{', '.join(INCIDENT_TYPES)}."
        )

    incident_id = incident_repository.insert(
        {
            "logistics_request_id": request_id,
            "incident_type": incident_type,
            "description": description,
            "status": "OPEN",
            "reported_by_user_id": user.id,
        }
    )

    logistics_repository.update(
        request_id,
        {
            "incident_status": "OPEN",
        },
    )

    if incident_type in (
        VEHICLE_BREAKDOWN,
        ACCIDENT,
        VEHICLE_UNAVAILABLE,
    ):
        if request.vehicle_id:
            vehicle_repository.update(
                request.vehicle_id,
                {
                    "is_available": 0,
                },
            )

    return incident_repository.find_by_id(
        incident_id
    )


def list_incidents(request_id, user):
    """List incidents reported against a logistics request."""
    request = logistics_repository.find_by_id(
        request_id
    )

    if not request:
        raise NotFoundError(
            "Logistics request not found."
        )

    is_requester = (
        request.requested_by_user_id == user.id
    )

    is_admin = user.role == ADMIN

    assigned_transporter = None

    if user.role == TRANSPORTER:
        assigned_transporter = (
            transporter_repository.find_by_user_id(
                user.id
            )
        )

    is_assigned_transporter = (
        assigned_transporter is not None
        and request.transporter_id
        == assigned_transporter.id
    )

    allowed = (
        is_admin
        or is_requester
        or is_assigned_transporter
    )

    if not allowed:
        raise ForbiddenError(
            "You are not allowed to view incidents "
            "for this request."
        )

    incidents = incident_repository.for_request(
        request_id
    )

    return [
        incident.to_dict()
        for incident in incidents
    ]


def update_incident(
    incident_id,
    status,
    resolution_notes,
    user,
):
    """Update the status of a logistics incident."""
    incident = incident_repository.find_by_id(
        incident_id
    )

    if not incident:
        raise NotFoundError(
            "Incident not found."
        )

    if user.role != ADMIN:
        raise ForbiddenError(
            "Only an administrator can resolve "
            "logistics incidents."
        )

    status = status.upper()

    if status not in INCIDENT_STATUSES:
        raise ValidationError(
            f"'status' must be one of: "
            f"{', '.join(INCIDENT_STATUSES)}."
        )

    payload = {
        "status": status,
        "resolution_notes": resolution_notes,
    }

    if status == "RESOLVED":
        payload["resolved_at"] = (
            dt.datetime.now()
        )

    incident_repository.update(
        incident_id,
        payload,
    )

    request = logistics_repository.find_by_id(
        incident.logistics_request_id
    )

    if request:
        remaining = incident_repository.for_request(
            incident.logistics_request_id
        )

        has_open_incident = any(
            item.status in (
                "OPEN",
                "IN_PROGRESS",
            )
            for item in remaining
        )

        logistics_repository.update(
            incident.logistics_request_id,
            {
                "incident_status": (
                    "OPEN"
                    if has_open_incident
                    else "NONE"
                ),
            },
        )

    return incident_repository.find_by_id(
        incident_id
    )