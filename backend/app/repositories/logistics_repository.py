"""Transport requests raised against a lot or transaction."""
from app.config import db
from app.models import rows_to_dicts
from app.models.logistics_request import LogisticsRequest
from app.repositories import BaseRepository, Filter

_LOGISTICS_JOIN_SELECT = """
    SELECT lr.*, t.transaction_code, l.lot_code, c.name AS crop_name,
           u.name AS requested_by_name, u.phone AS requested_by_phone
    FROM logistics_requests lr
    LEFT JOIN transactions t ON t.id = lr.transaction_id
    LEFT JOIN lots l ON l.id = lr.lot_id
    LEFT JOIN crops c ON c.id = l.crop_id
    JOIN users u ON u.id = lr.requested_by_user_id
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


logistics_repository = LogisticsRepository()
