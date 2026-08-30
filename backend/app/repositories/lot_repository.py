"""Farmer/FPO lots and the member contributions inside aggregated lots."""
from app.config import db
from app.models import rows_to_dicts
from app.models.lot import Lot
from app.models.lot_contribution import LotContribution
from app.repositories import BaseRepository, Filter

#: Columns joined onto a lot so a list view can render without extra requests.
_LOT_JOIN_SELECT = """
    SELECT l.*, c.name AS crop_name, c.category AS crop_category,
           c.is_perishable, u.name AS seller_name, u.phone AS seller_phone,
           (SELECT COUNT(*) FROM offers o
             WHERE o.lot_id = l.id AND o.status = 'PENDING') AS pending_offer_count
    FROM lots l
    JOIN crops c ON c.id = l.crop_id
    JOIN users u ON u.id = l.seller_user_id
"""


#: Integer columns that must surface as real booleans, matching the models.
_LOT_BOOL_COLUMNS = ("is_aggregated", "is_perishable")


def enrich_lot(row):
    """
    Normalise a joined lot row so it matches ``Lot.to_dict()``.

    MySQL and SQLite both store these flags as 0/1. Without this, the same
    field would be ``1`` from a list endpoint and ``true`` from a model
    endpoint, and the frontend would have to handle both.
    """
    if not row:
        return row
    for column in _LOT_BOOL_COLUMNS:
        if row.get(column) is not None:
            row[column] = bool(row[column])
    return row


class LotRepository(BaseRepository):
    table = "lots"
    model = Lot
    sortable_columns = ("id", "created_at", "quantity", "harvest_date", "expected_price")
    default_order = "created_at DESC, id DESC"

    def find_by_code(self, lot_code):
        return self.find_one_by("lot_code", lot_code)

    def next_code(self):
        """Human-readable lot reference the farmer can quote over the phone."""
        last_id = db.query_scalar("SELECT MAX(id) AS m FROM lots", (), 0) or 0
        return f"LOT{int(last_id) + 1:06d}"

    def detail(self, lot_id):
        rows = db.query_all(_LOT_JOIN_SELECT + " WHERE l.id = ?", (lot_id,))
        return enrich_lot(rows_to_dicts(rows)[0]) if rows else None

    def search(self, seller_user_id=None, crop_id=None, status=None, statuses=None,
               district=None, state=None, grade=None, fpo_id=None,
               min_quantity=None, max_quantity=None, available_from=None,
               page=1, page_size=20, order_by=None):
        filters = Filter()
        filters.eq("l.seller_user_id", seller_user_id)
        filters.eq("l.crop_id", crop_id)
        filters.eq("l.status", status)
        filters.in_("l.status", statuses)
        filters.eq("l.district", district)
        filters.eq("l.state", state)
        filters.eq("l.grade", grade)
        filters.eq("l.fpo_id", fpo_id)
        filters.gte("l.quantity", min_quantity)
        filters.lte("l.quantity", max_quantity)
        filters.gte("l.available_from", available_from)

        where_sql, params = filters.where_sql()
        # Every filter above is on the lots table, so the count needs no joins.
        total = int(
            db.query_scalar(f"SELECT COUNT(*) AS c FROM lots l{where_sql}", params, 0) or 0
        )
        order = self.safe_order(order_by).replace("created_at", "l.created_at")
        rows = db.query_all(
            f"{_LOT_JOIN_SELECT}{where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
            params + [int(page_size), int((page - 1) * page_size)],
        )
        return [enrich_lot(row) for row in rows_to_dicts(rows)], total

    def open_lots_for_crop(self, crop_id, exclude_lot_id=None, limit=100):
        """Live sell-side supply for one crop, used when matching a buyer demand."""
        sql = _LOT_JOIN_SELECT + " WHERE l.crop_id = ? AND l.status IN ('LISTED', 'OFFER_RECEIVED')"
        params = [crop_id]
        if exclude_lot_id:
            sql += " AND l.id <> ?"
            params.append(exclude_lot_id)
        sql += " ORDER BY l.created_at DESC LIMIT ?"
        params.append(int(limit))
        return [enrich_lot(row) for row in rows_to_dicts(db.query_all(sql, params))]

    def set_status(self, lot_id, status):
        return self.update(lot_id, {"status": status})

    def expire_stale(self, today):
        """Mark listed lots whose availability window has closed."""
        return db.execute(
            """
            UPDATE lots SET status = 'EXPIRED'
            WHERE status IN ('LISTED', 'OFFER_RECEIVED')
              AND available_until IS NOT NULL AND available_until < ?
            """,
            (today,),
        )

    def seller_summary(self, seller_user_id):
        """Counts for the farmer dashboard header."""
        row = db.query_one(
            """
            SELECT COUNT(*) AS total_lots,
                   SUM(CASE WHEN status IN ('LISTED','OFFER_RECEIVED') THEN 1 ELSE 0 END) AS active_lots,
                   SUM(CASE WHEN status = 'SOLD' THEN 1 ELSE 0 END) AS sold_lots,
                   SUM(CASE WHEN status IN ('LISTED','OFFER_RECEIVED') THEN quantity ELSE 0 END) AS active_quantity
            FROM lots WHERE seller_user_id = ?
            """,
            (seller_user_id,),
        )
        return rows_to_dicts([row])[0] if row else {}


class LotContributionRepository(BaseRepository):
    table = "lot_contributions"
    model = LotContribution
    has_updated_at = False

    def list_for_lot(self, lot_id):
        return self.find_where(Filter().eq("lot_id", lot_id))

    def detailed_for_lot(self, lot_id):
        rows = db.query_all(
            """
            SELECT lc.*, u.name AS farmer_name, u.phone AS farmer_phone, f.village
            FROM lot_contributions lc
            JOIN farmer_profiles f ON f.id = lc.farmer_id
            JOIN users u ON u.id = f.user_id
            WHERE lc.lot_id = ?
            ORDER BY lc.quantity DESC
            """,
            (lot_id,),
        )
        return rows_to_dicts(rows)

    def total_quantity(self, lot_id):
        return float(
            db.query_scalar(
                "SELECT SUM(quantity) AS q FROM lot_contributions WHERE lot_id = ?", (lot_id,), 0
            )
            or 0
        )

    def record_payouts(self, lot_id, net_amount):
        """
        Split a settled amount across contributors, pro rata by quantity.

        Rounding is absorbed by the largest contributor so the parts always add
        back up to the whole.
        """
        contributions = self.list_for_lot(lot_id)
        total = sum(float(c.quantity or 0) for c in contributions)
        if not contributions or total <= 0:
            return []
        payouts = []
        running = 0.0
        ordered = sorted(contributions, key=lambda c: float(c.quantity or 0))
        for index, contribution in enumerate(ordered):
            if index == len(ordered) - 1:
                amount = round(float(net_amount) - running, 2)
            else:
                amount = round(float(net_amount) * float(contribution.quantity) / total, 2)
                running += amount
            self.update(contribution.id, {"payout_amount": amount})
            payouts.append({"contribution_id": contribution.id,
                            "farmer_id": contribution.farmer_id,
                            "quantity": float(contribution.quantity),
                            "payout_amount": amount})
        return payouts


lot_repository = LotRepository()
lot_contribution_repository = LotContributionRepository()
