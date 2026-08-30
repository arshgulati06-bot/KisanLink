"""
A request to move a lot from the farm gate to the buyer.

Costs here are ESTIMATES from the model in services/logistics_service.py, not
quotes from a transport provider.
"""
from dataclasses import dataclass

from app.models import BaseModel

REQUESTED = "REQUESTED"
ASSIGNED = "ASSIGNED"
IN_TRANSIT = "IN_TRANSIT"
DELIVERED = "DELIVERED"
CANCELLED = "CANCELLED"
STATUSES = (REQUESTED, ASSIGNED, IN_TRANSIT, DELIVERED, CANCELLED)

#: Allowed forward moves. Anything else is rejected by the service layer.
STATUS_FLOW = {
    REQUESTED: (ASSIGNED, CANCELLED),
    ASSIGNED: (IN_TRANSIT, CANCELLED),
    IN_TRANSIT: (DELIVERED, CANCELLED),
    DELIVERED: (),
    CANCELLED: (),
}

VEHICLE_TYPES = ("TRACTOR_TROLLEY", "TEMPO", "PICKUP", "TRUCK_9T", "TRUCK_16T")


@dataclass
class LogisticsRequest(BaseModel):
    FLOAT_FIELDS = (
        "pickup_latitude",
        "pickup_longitude",
        "drop_latitude",
        "drop_longitude",
        "distance_km",
        "quantity",
        "estimated_cost",
        "actual_cost",
    )

    id: int = None
    transaction_id: int = None
    lot_id: int = None
    requested_by_user_id: int = None
    pickup_address: str = None
    pickup_district: str = None
    pickup_latitude: float = None
    pickup_longitude: float = None
    drop_address: str = None
    drop_district: str = None
    drop_latitude: float = None
    drop_longitude: float = None
    distance_km: float = None
    vehicle_type: str = None
    quantity: float = None
    unit: str = "QUINTAL"
    estimated_cost: float = None
    actual_cost: float = None
    scheduled_date: str = None
    status: str = REQUESTED
    provider_name: str = None
    provider_phone: str = None
    notes: str = None
    created_at: str = None
    updated_at: str = None
