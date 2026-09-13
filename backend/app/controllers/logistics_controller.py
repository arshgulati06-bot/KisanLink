"""Transport estimate, transport requests, and transportation endpoints."""
from app.controllers import body, page_args, query
from app.middleware.auth_middleware import login_required, require_current_user
from app.schemas.logistics_schema import (
    ASSIGN_PROVIDER_SCHEMA,
    CREATE_INCIDENT_SCHEMA,
    CREATE_REQUEST_SCHEMA,
    CREATE_TRANSPORTER_SCHEMA,
    CREATE_VEHICLE_SCHEMA,
    ETA_UPDATE_SCHEMA,
    ESTIMATE_SCHEMA,
    REASSIGN_SCHEMA,
    REQUEST_FILTER_SCHEMA,
    TRANSPORTER_FILTER_SCHEMA,
    UPDATE_INCIDENT_SCHEMA,
    UPDATE_STATUS_SCHEMA,
    VEHICLE_FILTER_SCHEMA,
)
from app.services import logistics_service
from app.utils.responses import created, paginated, success


# ---------------------------------------------------------------------------
# Transport estimate
# ---------------------------------------------------------------------------

def estimate():
    """
    Estimate transport cost.

    Accepts either an explicit ``distance_km`` or two locations to measure
    between. Always returns the assumptions used.
    """
    data = body(ESTIMATE_SCHEMA)

    if data.get("distance_km") is not None:
        result = logistics_service.estimate_transport(
            data["quantity"],
            data.get("unit", "QUINTAL"),
            data["distance_km"],
        )
    else:
        result = logistics_service.estimate_between(
            {
                "latitude": data.get("from_latitude"),
                "longitude": data.get("from_longitude"),
                "district": data.get("from_district"),
            },
            {
                "latitude": data.get("to_latitude"),
                "longitude": data.get("to_longitude"),
                "district": data.get("to_district"),
            },
            data["quantity"],
            data.get("unit", "QUINTAL"),
        )

    return success(result)


# ---------------------------------------------------------------------------
# Logistics requests
# ---------------------------------------------------------------------------

@login_required
def create_request():
    return created(
        logistics_service.create_request(
            require_current_user(),
            body(CREATE_REQUEST_SCHEMA),
        ),
        message="Transport request raised.",
    )


@login_required
def list_requests():
    page, page_size = page_args()
    filters = query(REQUEST_FILTER_SCHEMA)

    items, total = logistics_service.list_requests(
        user=require_current_user(),
        page=page,
        page_size=page_size,
        **filters,
    )

    return paginated(
        items,
        page,
        page_size,
        total,
    )


@login_required
def get_request(request_id):
    return success(
        logistics_service.get_request(request_id)
    )


@login_required
def update_status(request_id):
    data = body(UPDATE_STATUS_SCHEMA)

    return success(
        logistics_service.update_status(
            request_id,
            data["status"],
            require_current_user(),
            notes=data.get("notes"),
            actual_cost=data.get("actual_cost"),
        ),
        message=f"Transport request moved to {data['status']}.",
    )


@login_required
def assign_provider(request_id):
    data = body(ASSIGN_PROVIDER_SCHEMA)

    return success(
        logistics_service.assign_provider(
            request_id,
            data["provider_name"],
            data.get("provider_phone"),
            require_current_user(),
            data.get("scheduled_date"),
        ),
        message="Transport provider assigned.",
    )


# ---------------------------------------------------------------------------
# Transporter management
# ---------------------------------------------------------------------------

@login_required
def create_transporter():
    data = body(CREATE_TRANSPORTER_SCHEMA)

    return created(
        logistics_service.register_transporter(
            require_current_user(),
            data,
        ),
        message="Transporter profile created.",
    )


@login_required
def list_transporters():
    page, page_size = page_args()
    filters = query(TRANSPORTER_FILTER_SCHEMA)

    result = logistics_service.list_transporters(
        district=filters.get("district"),
        verification_status=filters.get("verification_status"),
        query=filters.get("q"),
        page=page,
        page_size=page_size,
    )

    return paginated(
        result["items"],
        result["page"],
        result["page_size"],
        result["total"],
    )


# ---------------------------------------------------------------------------
# Vehicle management
# ---------------------------------------------------------------------------

@login_required
def create_vehicle():
    data = body(CREATE_VEHICLE_SCHEMA)

    return created(
        logistics_service.register_vehicle(
            require_current_user(),
            data,
        ),
        message="Vehicle registered.",
    )


@login_required
def list_available_vehicles():
    filters = query(VEHICLE_FILTER_SCHEMA)

    return success(
        logistics_service.list_available_vehicles(
            vehicle_type=filters.get("vehicle_type"),
            min_capacity=filters.get("min_capacity"),
            transporter_id=filters.get("transporter_id"),
        )
    )


# ---------------------------------------------------------------------------
# Transport assignment and backup
# ---------------------------------------------------------------------------

@login_required
def assign_transporter(request_id):
    data = body(REASSIGN_SCHEMA)

    return success(
        logistics_service.assign_transporter(
            request_id,
            data["transporter_id"],
            data["vehicle_id"],
            require_current_user(),
        ),
        message="Transporter and vehicle assigned.",
    )


@login_required
def backup_options(request_id):
    return success(
        logistics_service.get_backup_options(
            request_id
        )
    )


@login_required
def reassign_transport(request_id):
    data = body(REASSIGN_SCHEMA)

    return success(
        logistics_service.reassign_transport(
            request_id,
            data["transporter_id"],
            data["vehicle_id"],
            require_current_user(),
        ),
        message="Transport reassigned successfully.",
    )


# ---------------------------------------------------------------------------
# ETA and route progress
# ---------------------------------------------------------------------------

@login_required
def update_eta_progress(request_id):
    data = body(ETA_UPDATE_SCHEMA)

    return success(
        logistics_service.update_eta_progress(
            request_id,
            data["eta_minutes"],
            route_status=data.get("route_status"),
            route_progress_percent=data.get(
                "route_progress_percent"
            ),
            user=require_current_user(),
        ),
        message="ETA and route progress updated.",
    )


# ---------------------------------------------------------------------------
# Logistics incidents
# ---------------------------------------------------------------------------

@login_required
def create_incident(request_id):
    data = body(CREATE_INCIDENT_SCHEMA)

    return created(
        logistics_service.report_incident(
            request_id,
            data["incident_type"],
            data["description"],
            require_current_user(),
        ),
        message="Logistics incident reported.",
    )


@login_required
def list_incidents(request_id):
    return success(
        logistics_service.list_incidents(
            request_id,
            require_current_user(),
        )
    )


@login_required
def update_incident(incident_id):
    data = body(UPDATE_INCIDENT_SCHEMA)

    return success(
        logistics_service.update_incident(
            incident_id,
            data["status"],
            data.get("resolution_notes"),
            require_current_user(),
        ),
        message="Logistics incident updated.",
    )