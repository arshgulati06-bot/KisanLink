"""Storage facility and holding-cost endpoints."""
from app.controllers import body, page_args, query
from app.middleware.role_middleware import admin_required
from app.schemas.storage_schema import (
    CREATE_FACILITY_SCHEMA,
    FACILITY_FILTER_SCHEMA,
    NEARBY_FACILITY_SCHEMA,
    STORAGE_ESTIMATE_SCHEMA,
)
from app.services import storage_service
from app.utils.responses import ValidationError, created, paginated, success


def list_facilities():
    page, page_size = page_args()
    filters = query(FACILITY_FILTER_SCHEMA)
    items, total = storage_service.list_facilities(
        district=filters.get("district"),
        state=filters.get("state"),
        facility_type=filters.get("facility_type"),
        cold_only=filters.get("cold_only", False),
        min_available_tonnes=filters.get("min_available_tonnes"),
        page=page,
        page_size=page_size,
        order_by=filters.get("order_by"),
    )
    return paginated(items, page, page_size, total)


def get_facility(facility_id):
    return success(storage_service.get_facility(facility_id).to_dict())


def nearby():
    filters = query(NEARBY_FACILITY_SCHEMA)
    if filters.get("latitude") is None and not filters.get("district"):
        raise ValidationError(
            "Provide either 'latitude' and 'longitude', or a 'district', to find storage nearby."
        )
    return success(
        storage_service.nearby_facilities(
            latitude=filters.get("latitude"),
            longitude=filters.get("longitude"),
            district=filters.get("district"),
            state=filters.get("state"),
            required_tonnes=filters.get("required_tonnes"),
            cold_storage=filters.get("cold_storage", False),
            limit=filters.get("limit", 10),
            max_distance_km=filters.get("max_distance_km", 150),
        )
    )


def estimate():
    """What it would cost to hold this quantity for a number of days."""
    data = body(STORAGE_ESTIMATE_SCHEMA)
    facility = (
        storage_service.get_facility(data["facility_id"]) if data.get("facility_id") else None
    )
    per_unit, detail = storage_service.holding_cost_per_unit(
        data["quantity"],
        data.get("unit", "QUINTAL"),
        data["days"],
        data.get("price_per_unit"),
        facility=facility,
        crop_is_perishable=data.get("is_perishable", False),
    )
    return success({"holding_cost_per_unit": per_unit, **detail})


@admin_required
def create_facility():
    return created(
        storage_service.create_facility(body(CREATE_FACILITY_SCHEMA)),
        message="Storage facility added.",
    )
