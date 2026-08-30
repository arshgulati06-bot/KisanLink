"""Transport estimate and transport request endpoints."""
from app.controllers import body, page_args, query
from app.middleware.auth_middleware import login_required, require_current_user
from app.schemas.logistics_schema import (
    ASSIGN_PROVIDER_SCHEMA,
    CREATE_REQUEST_SCHEMA,
    ESTIMATE_SCHEMA,
    REQUEST_FILTER_SCHEMA,
    UPDATE_STATUS_SCHEMA,
)
from app.services import logistics_service
from app.utils.responses import created, paginated, success


def estimate():
    """
    Estimate transport cost.

    Accepts either an explicit ``distance_km`` or two locations to measure
    between. Always returns the assumptions used.
    """
    data = body(ESTIMATE_SCHEMA)
    if data.get("distance_km") is not None:
        result = logistics_service.estimate_transport(
            data["quantity"], data.get("unit", "QUINTAL"), data["distance_km"]
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


@login_required
def create_request():
    return created(
        logistics_service.create_request(require_current_user(), body(CREATE_REQUEST_SCHEMA)),
        message="Transport request raised.",
    )


@login_required
def list_requests():
    page, page_size = page_args()
    filters = query(REQUEST_FILTER_SCHEMA)
    items, total = logistics_service.list_requests(
        user=require_current_user(), page=page, page_size=page_size, **filters
    )
    return paginated(items, page, page_size, total)


@login_required
def get_request(request_id):
    return success(logistics_service.get_request(request_id))


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
