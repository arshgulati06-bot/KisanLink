"""Storage facility directory."""
from app.models.storage_facility import StorageFacility
from app.repositories import BaseRepository, Filter


class StorageRepository(BaseRepository):
    table = "storage_facilities"
    model = StorageFacility
    sortable_columns = ("id", "name", "cost_per_tonne_per_day", "capacity_tonnes")
    default_order = "name ASC"
    has_updated_at = False

    def search(self, district=None, state=None, facility_type=None, cold_only=False,
               min_available_tonnes=None, page=1, page_size=20, order_by=None):
        filters = Filter().eq("is_active", 1)
        filters.eq("district", district)
        filters.eq("state", state)
        filters.eq("facility_type", facility_type)
        if cold_only:
            filters.eq("has_cold_storage", 1)
        filters.gte("available_capacity_tonnes", min_available_tonnes)
        total = self.count_where(filters)
        rows = self.find_where(
            filters, order_by=order_by, limit=page_size, offset=(page - 1) * page_size
        )
        return rows, total

    def with_coordinates(self, state=None):
        filters = (
            Filter().eq("is_active", 1).add("latitude IS NOT NULL").add("longitude IS NOT NULL")
        )
        filters.eq("state", state)
        return self.find_where(filters)

    def reserve_capacity(self, facility_id, tonnes):
        """Reduce free capacity, never below zero."""
        facility = self.find_by_id(facility_id)
        if not facility or facility.available_capacity_tonnes is None:
            return None
        remaining = max(0.0, float(facility.available_capacity_tonnes) - float(tonnes))
        self.update(facility_id, {"available_capacity_tonnes": remaining})
        return remaining


storage_repository = StorageRepository()
