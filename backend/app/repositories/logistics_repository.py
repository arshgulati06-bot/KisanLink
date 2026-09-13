"""Transport requests raised against a lot or transaction."""
from app.config import db
from app.models import rows_to_dicts
from app.models.logistics_request import LogisticsRequest
from app.repositories import BaseRepository, Filter

_LOGISTICS_JOIN_SELECT = """
    SELECT
        lr.*,
        t.transaction_code,
        l.lot_code,
        c.name AS crop_name,
        u.name AS requested_by_name,
        u.phone AS requested_by_phone,
        tr.business_name AS transporter_name,
        tr.phone AS transporter_phone,
        tr.rating AS transporter_rating,
        tr.reliability_score AS transporter_reliability_score,
        v.vehicle_type AS assigned_vehicle_type,
        v.vehicle_number AS assigned_vehicle_number,
        v.capacity_tonnes AS assigned_vehicle_capacity
    FROM logistics_requests lr
    LEFT JOIN transactions t ON t.id = lr.transaction_id
    LEFT JOIN lots l ON l.id = lr.lot_id
    LEFT JOIN crops c ON c.id = l.crop_id
    JOIN users u ON u.id = lr.requested_by_user_id
    LEFT JOIN transporters tr ON tr.id = lr.transporter_id
    LEFT JOIN vehicles v ON v.id = lr.vehicle_id
"""

class LogisticsRepository(BaseRepository):
    table = "logistics_requests"
    model = LogisticsRequest
    sortable_columns = ("id", "created_at", "scheduled_date", "estimated_cost")
    default_order = "created_at DESC"

    def detail(self, request_id):
        rows = db.query_all(_LOGISTICS_JOIN_SELECT + " WHERE lr.id = ?", (request_id,))
        return rows_to_dicts(rows)[0] if rows else None

    def search(self, requested_by_user_id=None, transaction_id=None, lot_id=None,
               status=None, page=1, page_size=20, order_by=None):
        filters = Filter()
        filters.eq("lr.requested_by_user_id", requested_by_user_id)
        filters.eq("lr.transaction_id", transaction_id)
        filters.eq("lr.lot_id", lot_id)
        filters.eq("lr.status", status)
        where_sql, params = filters.where_sql()
        total = int(
            db.query_scalar(
                f"SELECT COUNT(*) AS c FROM logistics_requests lr{where_sql}", params, 0
            )
            or 0
        )
        order = self.safe_order(order_by)
        order = order if order.startswith("lr.") else f"lr.{order}"
        rows = db.query_all(
            f"{_LOGISTICS_JOIN_SELECT}{where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
            params + [int(page_size), int((page - 1) * page_size)],
        )
        return rows_to_dicts(rows), total

    def for_transaction(self, transaction_id):
        return self.find_where(Filter().eq("transaction_id", transaction_id))

    def backup_options(self, request_id, min_capacity=0):
        request = self.detail(request_id)

        if not request:
            return []

        current_transporter_id = request.get("transporter_id")

        rows = db.query_all(
            """
            SELECT
                v.id AS vehicle_id,
                v.vehicle_type,
                v.vehicle_number,
                v.capacity_tonnes,
                v.service_area,
                v.rate_per_km,
                tr.id AS transporter_id,
                tr.business_name AS transporter_name,
                tr.phone AS transporter_phone,
                tr.rating AS transporter_rating,
                tr.reliability_score AS transporter_reliability_score
            FROM vehicles v
            JOIN transporters tr
                ON tr.id = v.transporter_id
            WHERE v.is_available = 1
              AND tr.is_available = 1
              AND v.capacity_tonnes >= ?
              AND (? IS NULL OR tr.id <> ?)
            ORDER BY
                tr.reliability_score DESC,
                v.capacity_tonnes ASC,
                v.id ASC
            """,
            (
                float(min_capacity or 0),
                current_transporter_id,
                current_transporter_id,
            ),
        )

        return rows_to_dicts(rows)


logistics_repository = LogisticsRepository()
