"""Digital offers and counter-offers on lots."""
from app.config import db
from app.models import rows_to_dicts
from app.models.offer import Offer
from app.repositories import BaseRepository, Filter, utcnow

_OFFER_JOIN_SELECT = """
    SELECT o.*, l.lot_code, l.crop_id, l.grade AS lot_grade, l.quantity AS lot_quantity,
           l.district AS lot_district, l.status AS lot_status,
           c.name AS crop_name,
           b.business_name, b.buyer_type, b.verification_status, b.trust_score,
           b.district AS buyer_district,
           u.name AS seller_name
    FROM offers o
    JOIN lots l ON l.id = o.lot_id
    JOIN crops c ON c.id = l.crop_id
    JOIN buyer_profiles b ON b.id = o.buyer_id
    JOIN users u ON u.id = o.seller_user_id
"""


def enrich_offer(row):
    """Add the derived total the Offer model exposes, so joins match models."""
    if not row:
        return row
    row["gross_amount"] = round(
        float(row.get("price_per_unit") or 0) * float(row.get("quantity") or 0), 2
    )
    return row


class OfferRepository(BaseRepository):
    table = "offers"
    model = Offer
    sortable_columns = ("id", "created_at", "price_per_unit", "quantity", "valid_until")
    default_order = "created_at DESC, id DESC"

    def detail(self, offer_id):
        rows = db.query_all(_OFFER_JOIN_SELECT + " WHERE o.id = ?", (offer_id,))
        return enrich_offer(rows_to_dicts(rows)[0]) if rows else None

    def search(self, lot_id=None, buyer_id=None, seller_user_id=None, status=None,
               statuses=None, crop_id=None, page=1, page_size=20, order_by=None):
        filters = Filter()
        filters.eq("o.lot_id", lot_id)
        filters.eq("o.buyer_id", buyer_id)
        filters.eq("o.seller_user_id", seller_user_id)
        filters.eq("o.status", status)
        filters.in_("o.status", statuses)
        filters.eq("l.crop_id", crop_id)
        where_sql, params = filters.where_sql()
        total = int(
            db.query_scalar(
                "SELECT COUNT(*) AS c FROM offers o JOIN lots l ON l.id = o.lot_id" + where_sql,
                params,
                0,
            )
            or 0
        )
        order = self.safe_order(order_by)
        order = order if order.startswith("o.") else f"o.{order}"
        rows = db.query_all(
            f"{_OFFER_JOIN_SELECT}{where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
            params + [int(page_size), int((page - 1) * page_size)],
        )
        return [enrich_offer(row) for row in rows_to_dicts(rows)], total

    def live_offers_for_lot(self, lot_id):
        """Offers the farmer can still act on, best price first."""
        rows = db.query_all(
            _OFFER_JOIN_SELECT
            + " WHERE o.lot_id = ? AND o.status IN ('PENDING', 'COUNTERED')"
            " ORDER BY o.price_per_unit DESC",
            (lot_id,),
        )
        return [enrich_offer(row) for row in rows_to_dicts(rows)]

    def has_live_offer(self, lot_id, buyer_id):
        """One live offer per buyer per lot - a counter replaces, not stacks."""
        row = db.query_one(
            "SELECT id FROM offers WHERE lot_id = ? AND buyer_id = ? AND status = 'PENDING'",
            (lot_id, buyer_id),
        )
        return row is not None

    def set_status(self, offer_id, status, remarks=None):
        data = {"status": status, "responded_at": utcnow()}
        if remarks:
            data["message"] = remarks
        return self.update(offer_id, data)

    def reject_other_offers(self, lot_id, accepted_offer_id):
        """
        Once one offer is accepted the rest cannot stay pending.

        Doing this in one statement keeps the lot from having two winners.
        """
        return db.execute(
            """
            UPDATE offers SET status = 'REJECTED', responded_at = ?, updated_at = ?
            WHERE lot_id = ? AND id <> ? AND status IN ('PENDING', 'COUNTERED')
            """,
            (utcnow(), utcnow(), lot_id, accepted_offer_id),
        )

    def expire_stale(self, today):
        return db.execute(
            """
            UPDATE offers SET status = 'EXPIRED', updated_at = ?
            WHERE status = 'PENDING' AND valid_until IS NOT NULL AND valid_until < ?
            """,
            (utcnow(), today),
        )

    def best_offer_for_lot(self, lot_id):
        row = db.query_one(
            """
            SELECT * FROM offers
            WHERE lot_id = ? AND status IN ('PENDING', 'COUNTERED')
            ORDER BY price_per_unit DESC LIMIT 1
            """,
            (lot_id,),
        )
        return self.model.from_row(row) if row else None

    def count_for_lot(self, lot_id, statuses=None):
        filters = Filter().eq("lot_id", lot_id).in_("status", statuses)
        return self.count_where(filters)


offer_repository = OfferRepository()
