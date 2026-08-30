"""Ratings, grievances and the recommendation snapshots."""
from app.config import db
from app.models import rows_to_dicts
from app.models.grievance import Grievance
from app.models.rating import Rating
from app.models.recommendation import Recommendation
from app.repositories import BaseRepository, Filter, utcnow


class RatingRepository(BaseRepository):
    table = "ratings"
    model = Rating
    sortable_columns = ("id", "created_at", "score")
    default_order = "created_at DESC"
    has_updated_at = False

    def already_rated(self, transaction_id, rater_user_id):
        row = db.query_one(
            "SELECT id FROM ratings WHERE transaction_id = ? AND rater_user_id = ?",
            (transaction_id, rater_user_id),
        )
        return row is not None

    def for_user(self, rated_user_id, limit=50):
        rows = db.query_all(
            """
            SELECT r.*, u.name AS rater_name, u.role AS rater_role, t.transaction_code
            FROM ratings r
            JOIN users u ON u.id = r.rater_user_id
            JOIN transactions t ON t.id = r.transaction_id
            WHERE r.rated_user_id = ?
            ORDER BY r.created_at DESC LIMIT ?
            """,
            (rated_user_id, int(limit)),
        )
        return rows_to_dicts(rows)

    def aggregate_for_user(self, rated_user_id):
        row = db.query_one(
            """
            SELECT COUNT(*) AS rating_count,
                   AVG(score) AS average_score,
                   AVG(payment_score) AS average_payment_score,
                   AVG(quality_score) AS average_quality_score,
                   AVG(punctuality_score) AS average_punctuality_score
            FROM ratings WHERE rated_user_id = ?
            """,
            (rated_user_id,),
        )
        return rows_to_dicts([row])[0] if row else {}


class GrievanceRepository(BaseRepository):
    table = "grievances"
    model = Grievance
    sortable_columns = ("id", "created_at", "status")
    default_order = "created_at DESC"

    def next_ticket(self):
        last_id = db.query_scalar("SELECT MAX(id) AS m FROM grievances", (), 0) or 0
        return f"GRV{int(last_id) + 1:06d}"

    def detail(self, grievance_id):
        row = db.query_one(
            """
            SELECT g.*, t.transaction_code, r.name AS raised_by_name, r.role AS raised_by_role,
                   a.name AS against_name, h.name AS handled_by_name
            FROM grievances g
            LEFT JOIN transactions t ON t.id = g.transaction_id
            JOIN users r ON r.id = g.raised_by_user_id
            LEFT JOIN users a ON a.id = g.against_user_id
            LEFT JOIN users h ON h.id = g.handled_by_user_id
            WHERE g.id = ?
            """,
            (grievance_id,),
        )
        return rows_to_dicts([row])[0] if row else None

    def search(self, raised_by_user_id=None, against_user_id=None, status=None,
               category=None, transaction_id=None, page=1, page_size=20, order_by=None):
        filters = Filter()
        filters.eq("raised_by_user_id", raised_by_user_id)
        filters.eq("against_user_id", against_user_id)
        filters.eq("status", status)
        filters.eq("category", category)
        filters.eq("transaction_id", transaction_id)
        total = self.count_where(filters)
        rows = self.find_where(
            filters, order_by=order_by, limit=page_size, offset=(page - 1) * page_size
        )
        return rows, total

    def open_count_against(self, user_id):
        return int(
            db.query_scalar(
                "SELECT COUNT(*) AS c FROM grievances "
                "WHERE against_user_id = ? AND status IN ('OPEN', 'UNDER_REVIEW')",
                (user_id,),
                0,
            )
            or 0
        )

    def resolve(self, grievance_id, status, resolution, handled_by_user_id):
        return self.update(
            grievance_id,
            {
                "status": status,
                "resolution": resolution,
                "handled_by_user_id": handled_by_user_id,
                "resolved_at": utcnow(),
            },
        )


class RecommendationRepository(BaseRepository):
    table = "recommendations"
    model = Recommendation
    sortable_columns = ("id", "generated_at")
    default_order = "generated_at DESC, id DESC"
    has_updated_at = False

    def latest_for_lot(self, lot_id):
        row = db.query_one(
            "SELECT * FROM recommendations WHERE lot_id = ? ORDER BY generated_at DESC, id DESC LIMIT 1",
            (lot_id,),
        )
        return self.model.from_row(row) if row else None

    def history_for_lot(self, lot_id, limit=10):
        return self.find_where(Filter().eq("lot_id", lot_id), limit=limit, offset=0)


rating_repository = RatingRepository()
grievance_repository = GrievanceRepository()
recommendation_repository = RecommendationRepository()
