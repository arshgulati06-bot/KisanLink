"""FPO membership queries."""
from app.config import db
from app.models import rows_to_dicts
from app.models.fpo_member import FpoMember
from app.repositories import BaseRepository

MEMBER_DETAIL_SELECT = """
    SELECT fm.*, f.village, f.district, f.land_size_acres, f.primary_crops,
           u.id AS user_id, u.name AS farmer_name, u.phone AS farmer_phone
    FROM fpo_members fm
    JOIN farmer_profiles f ON f.id = fm.farmer_id
    JOIN users u ON u.id = f.user_id
"""


class FpoMemberRepository(BaseRepository):
    table = "fpo_members"
    model = FpoMember
    sortable_columns = ("id", "joined_at")
    default_order = "joined_at DESC"
    has_updated_at = False

    def find_membership(self, fpo_id, farmer_id):
        row = db.query_one(
            "SELECT * FROM fpo_members WHERE fpo_id = ? AND farmer_id = ?", (fpo_id, farmer_id)
        )
        return self.model.from_row(row) if row else None

    def list_members(self, fpo_id, status=None):
        sql = MEMBER_DETAIL_SELECT + " WHERE fm.fpo_id = ?"
        params = [fpo_id]
        if status:
            sql += " AND fm.status = ?"
            params.append(status)
        sql += " ORDER BY u.name ASC"
        return rows_to_dicts(db.query_all(sql, params))

    def memberships_for_farmer(self, farmer_id):
        rows = db.query_all(
            """
            SELECT fm.*, fp.fpo_name, fp.district, fp.registration_number
            FROM fpo_members fm
            JOIN fpo_profiles fp ON fp.id = fm.fpo_id
            WHERE fm.farmer_id = ?
            """,
            (farmer_id,),
        )
        return rows_to_dicts(rows)

    def is_active_member(self, fpo_id, farmer_id):
        membership = self.find_membership(fpo_id, farmer_id)
        return membership is not None and membership.status == "ACTIVE"

    def aggregation_candidates(self, fpo_id, crop_id):
        """
        Member lots that could be pooled into one FPO lot.

        Only DRAFT/LISTED lots with no live offer are eligible - a lot someone
        is already negotiating on must not be swept into an aggregate.
        """
        rows = db.query_all(
            """
            SELECT l.*, u.name AS farmer_name, f.id AS farmer_id, f.village
            FROM lots l
            JOIN users u ON u.id = l.seller_user_id
            JOIN farmer_profiles f ON f.user_id = u.id
            JOIN fpo_members fm ON fm.farmer_id = f.id
            WHERE fm.fpo_id = ? AND fm.status = 'ACTIVE'
              AND l.crop_id = ? AND l.status IN ('DRAFT', 'LISTED')
              AND l.is_aggregated = 0
              AND NOT EXISTS (
                    SELECT 1 FROM offers o
                    WHERE o.lot_id = l.id AND o.status IN ('PENDING', 'COUNTERED')
              )
            ORDER BY l.quantity DESC
            """,
            (fpo_id, crop_id),
        )
        return rows_to_dicts(rows)

    def fpo_summary(self, fpo_id):
        row = db.query_one(
            """
            SELECT
              (SELECT COUNT(*) FROM fpo_members WHERE fpo_id = ? AND status = 'ACTIVE') AS active_members,
              (SELECT COUNT(*) FROM lots WHERE fpo_id = ?) AS total_lots,
              (SELECT COUNT(*) FROM lots WHERE fpo_id = ? AND is_aggregated = 1) AS aggregated_lots,
              (SELECT COALESCE(SUM(quantity), 0) FROM lots
                WHERE fpo_id = ? AND status IN ('LISTED','OFFER_RECEIVED')) AS listed_quantity
            """,
            (fpo_id, fpo_id, fpo_id, fpo_id),
        )
        return rows_to_dicts([row])[0] if row else {}


fpo_member_repository = FpoMemberRepository()
