"""Commodity reference data."""
from app.models.crop import Crop
from app.repositories import BaseRepository, Filter


class CropRepository(BaseRepository):
    table = "crops"
    model = Crop
    sortable_columns = ("id", "name", "category")
    default_order = "name ASC"
    has_updated_at = False

    def find_by_name(self, name):
        return self.find_one_by("name", name)

    def search(self, query=None, category=None, active_only=True, page=1, page_size=50,
               order_by=None):
        filters = Filter()
        filters.like("name", query)
        filters.eq("category", category)
        if active_only:
            filters.eq("is_active", 1)
        total = self.count_where(filters)
        rows = self.find_where(
            filters, order_by=order_by, limit=page_size, offset=(page - 1) * page_size
        )
        return rows, total

    def name_taken(self, name, exclude_id=None):
        return self.exists("name", name, exclude_id)


crop_repository = CropRepository()
