"""Repository for logistics incident records."""
from app.models.logistics_incident import LogisticsIncident
from app.repositories import BaseRepository, Filter


class IncidentRepository(BaseRepository):
    table = "logistics_incidents"
    model = LogisticsIncident
    sortable_columns = (
        "id",
        "incident_type",
        "status",
        "reported_at",
        "created_at",
    )
    default_order = "created_at DESC"

    def for_request(self, logistics_request_id):
        filters = Filter().eq(
            "logistics_request_id",
            logistics_request_id,
        )
        return self.find_where(filters)


incident_repository = IncidentRepository()