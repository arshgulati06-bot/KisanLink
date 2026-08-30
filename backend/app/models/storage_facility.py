"""
A warehouse or cold store the farmer could use instead of selling immediately.

Storage matters to this problem statement specifically because a farmer with
nowhere to keep the crop has no option but to accept the first price offered.
"""
from dataclasses import dataclass

from app.models import BaseModel

WAREHOUSE = "WAREHOUSE"
COLD_STORAGE = "COLD_STORAGE"
FPO_GODOWN = "FPO_GODOWN"
WDRA_WAREHOUSE = "WDRA_WAREHOUSE"
FACILITY_TYPES = (WAREHOUSE, COLD_STORAGE, FPO_GODOWN, WDRA_WAREHOUSE, "OTHER")


@dataclass
class StorageFacility(BaseModel):
    BOOL_FIELDS = (
        "has_cold_storage",
        "offers_warehouse_receipt",
        "is_seed_data",
        "is_active",
    )
    FLOAT_FIELDS = (
        "latitude",
        "longitude",
        "capacity_tonnes",
        "available_capacity_tonnes",
        "cost_per_tonne_per_day",
    )

    id: int = None
    name: str = None
    facility_type: str = WAREHOUSE
    operator_name: str = None
    district: str = None
    state: str = "Maharashtra"
    address: str = None
    latitude: float = None
    longitude: float = None
    capacity_tonnes: float = None
    available_capacity_tonnes: float = None
    cost_per_tonne_per_day: float = None
    has_cold_storage: int = 0
    offers_warehouse_receipt: int = 0
    contact_phone: str = None
    is_seed_data: int = 0
    is_active: int = 1
    created_at: str = None
