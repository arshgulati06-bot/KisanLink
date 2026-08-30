"""Buyer demand records."""
from app.config import db
from app.models import rows_to_dicts
from app.models.buyer_requirement import ACTIVE_STATUSES, BuyerRequirement
from app.repositories import BaseRepository, Filter

_REQUIREMENT_JOIN_SELECT = """
    SELECT r.*, c.name AS crop_name, b.business_name, b.buyer_type,
           b.verification_status, b.trust_score, b.district AS buyer_district,
           b.latitude AS buyer_latitude, b.longitude AS buyer_longitude
    FROM buyer_requirements r
    JOIN crops c ON c.id = r.crop_id
    JOIN buyer_profiles b ON b.id = r.buyer_id
"""


def enrich_requirement(row):
    """
    Add the fields the model computes, so a joined row and a model row look
    identical to the frontend.

    Without this, ``GET /api/buyer-demands/<id>`` would be missing
    ``remaining_quantity`` and ``indicative_price`` that the list view has.
    """
    if not row:
        return row
    required = float(row.get("required_quantity") or 0)
    fulfilled = float(row.get("fulfilled_quantity") or 0)
    row["remaining_quantity"] = max(0.0, round(required - fulfilled, 2))

    low, high = row.get("price_min"), row.get("price_max")
    if low is not None and high is not None:
        indicative = (float(low) + float(high)) / 2.0
    elif high is not None:
        indicative = float(high)
    elif low is not None:
        indicative = float(low)
    else:
        indicative = None
    row["indicative_price"] = round(indicative, 2) if indicative is not None else None
    return row


class BuyerRequirementRepository(BaseRepository):
    table = "buyer_requirements"
    model = BuyerRequirement
    sortable_columns = ("id", "created_at", "required_quantity", "price_max", "valid_until")
    default_order = "created_at DESC, id DESC"

    def detail(self, requirement_id):
        rows = db.query_all(_REQUIREMENT_JOIN_SELECT + " WHERE r.id = ?", (requirement_id,))
        return enrich_requirement(rows_to_dicts(rows)[0]) if rows else None

    def search(self, buyer_id=None, crop_id=None, status=None, statuses=None,
               district=None, buyer_type=None, active_only=False,
               page=1, page_size=20, order_by=None):
        filters = Filter()
        filters.eq("r.buyer_id", buyer_id)
        filters.eq("r.crop_id", crop_id)
        filters.eq("r.status", status)
        filters.in_("r.status", statuses)
        filters.eq("r.delivery_district", district)
        filters.eq("b.buyer_type", buyer_type)
        if active_only:
            filters.in_("r.status", list(ACTIVE_STATUSES))
        where_sql, params = filters.where_sql()
        total = int(
            db.query_scalar(
                "SELECT COUNT(*) AS c FROM buyer_requirements r "
                "JOIN buyer_profiles b ON b.id = r.buyer_id" + where_sql,
                params,
                0,
            )
            or 0
        )
        order = self.safe_order(order_by)
        order = order if order.startswith("r.") else f"r.{order}"
        rows = db.query_all(
            f"{_REQUIREMENT_JOIN_SELECT}{where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
            params + [int(page_size), int((page - 1) * page_size)],
        )
        return [enrich_requirement(row) for row in rows_to_dicts(rows)], total

    def active_for_crop(self, crop_id, today=None, limit=200):
        """
        Every live demand for a crop - the candidate pool the matching engine
        scores a lot against.
        """
        sql = _REQUIREMENT_JOIN_SELECT + """
            WHERE r.crop_id = ? AND r.status IN ('OPEN', 'PARTIALLY_FULFILLED')
        """
        params = [crop_id]
        if today:
            sql += " AND (r.valid_until IS NULL OR r.valid_until >= ?)"
            params.append(today)
        sql += " ORDER BY r.price_max DESC LIMIT ?"
        params.append(int(limit))
        return [enrich_requirement(row) for row in rows_to_dicts(db.query_all(sql, params))]

    def add_fulfilled_quantity(self, requirement_id, quantity):
        """
        Book quantity against a demand and move its status along.

        Called when an offer is accepted, so a demand that is already met stops
        appearing in matching results.
        """
        requirement = self.find_by_id(requirement_id)
        if not requirement:
            return None
        fulfilled = float(requirement.fulfilled_quantity or 0) + float(quantity or 0)
        required = float(requirement.required_quantity or 0)
        fulfilled = min(fulfilled, required) if required else fulfilled
        status = requirement.status
        if required and fulfilled >= required:
            status = "FULFILLED"
        elif fulfilled > 0:
            status = "PARTIALLY_FULFILLED"
        self.update(requirement_id, {"fulfilled_quantity": fulfilled, "status": status})
        return self.find_by_id(requirement_id)

    def expire_stale(self, today):
        return db.execute(
            """
            UPDATE buyer_requirements SET status = 'EXPIRED'
            WHERE status IN ('OPEN', 'PARTIALLY_FULFILLED')
              AND valid_until IS NOT NULL AND valid_until < ?
            """,
            (today,),
        )

    def buyer_summary(self, buyer_id):
        row = db.query_one(
            """
            SELECT COUNT(*) AS total_requirements,
                   SUM(CASE WHEN status IN ('OPEN','PARTIALLY_FULFILLED') THEN 1 ELSE 0 END) AS active_requirements,
                   SUM(CASE WHEN status IN ('OPEN','PARTIALLY_FULFILLED')
                            THEN required_quantity - fulfilled_quantity ELSE 0 END) AS open_quantity
            FROM buyer_requirements WHERE buyer_id = ?
            """,
            (buyer_id,),
        )
        return rows_to_dicts([row])[0] if row else {}


buyer_requirement_repository = BuyerRequirementRepository()
