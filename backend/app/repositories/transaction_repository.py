"""Transactions, their status trail, and payment records."""
from app.config import db
from app.models import rows_to_dicts
from app.models.payment import Payment
from app.models.transaction import Transaction, TransactionStatusHistory
from app.repositories import BaseRepository, Filter, utcnow

_TRANSACTION_JOIN_SELECT = """
    SELECT t.*, l.lot_code, l.grade AS lot_grade, c.name AS crop_name,
           b.business_name, b.buyer_type, b.verification_status,
           bu.name AS buyer_contact_name, bu.phone AS buyer_contact_phone,
           s.name AS seller_name, s.phone AS seller_phone,
           (SELECT COALESCE(SUM(p.amount), 0) FROM payments p
             WHERE p.transaction_id = t.id AND p.status = 'PAID') AS amount_paid
    FROM transactions t
    JOIN lots l ON l.id = t.lot_id
    JOIN crops c ON c.id = t.crop_id
    JOIN buyer_profiles b ON b.id = t.buyer_id
    JOIN users bu ON bu.id = b.user_id
    JOIN users s ON s.id = t.seller_user_id
"""


#: Statuses from which a transaction can no longer move.
_TERMINAL_STATUSES = ("COMPLETED", "CANCELLED")


def enrich_transaction(row):
    """
    Add the derived fields the Transaction model exposes.

    ``net_price_per_unit`` is the number that actually answers "what did the
    farmer get per quintal", so it must never be missing from a detail view.
    """
    if not row:
        return row
    quantity = float(row.get("quantity") or 0)
    net = float(row.get("net_amount") or 0)
    row["net_price_per_unit"] = round(net / quantity, 2) if quantity else None
    row["is_terminal"] = row.get("status") in _TERMINAL_STATUSES
    return row


class TransactionRepository(BaseRepository):
    table = "transactions"
    model = Transaction
    sortable_columns = ("id", "created_at", "gross_amount", "net_amount")
    default_order = "created_at DESC, id DESC"

    def next_code(self):
        last_id = db.query_scalar("SELECT MAX(id) AS m FROM transactions", (), 0) or 0
        return f"TXN{int(last_id) + 1:06d}"

    def find_by_offer(self, offer_id):
        return self.find_one_by("offer_id", offer_id)

    def detail(self, transaction_id):
        rows = db.query_all(_TRANSACTION_JOIN_SELECT + " WHERE t.id = ?", (transaction_id,))
        return enrich_transaction(rows_to_dicts(rows)[0]) if rows else None

    def search(self, seller_user_id=None, buyer_id=None, status=None, statuses=None,
               crop_id=None, lot_id=None, page=1, page_size=20, order_by=None):
        filters = Filter()
        filters.eq("t.seller_user_id", seller_user_id)
        filters.eq("t.buyer_id", buyer_id)
        filters.eq("t.status", status)
        filters.in_("t.status", statuses)
        filters.eq("t.crop_id", crop_id)
        filters.eq("t.lot_id", lot_id)
        where_sql, params = filters.where_sql()
        total = int(
            db.query_scalar(f"SELECT COUNT(*) AS c FROM transactions t{where_sql}", params, 0) or 0
        )
        order = self.safe_order(order_by)
        order = order if order.startswith("t.") else f"t.{order}"
        rows = db.query_all(
            f"{_TRANSACTION_JOIN_SELECT}{where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
            params + [int(page_size), int((page - 1) * page_size)],
        )
        return [enrich_transaction(row) for row in rows_to_dicts(rows)], total

    def party_summary(self, seller_user_id=None, buyer_id=None):
        """Totals for a dashboard: how many deals, how much actually realised."""
        column, value = ("seller_user_id", seller_user_id) if seller_user_id else ("buyer_id", buyer_id)
        row = db.query_one(
            f"""
            SELECT COUNT(*) AS total_transactions,
                   SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
                   SUM(CASE WHEN status IN ('CANCELLED') THEN 1 ELSE 0 END) AS cancelled,
                   SUM(CASE WHEN status = 'DISPUTED' THEN 1 ELSE 0 END) AS disputed,
                   COALESCE(SUM(gross_amount), 0) AS total_gross,
                   COALESCE(SUM(net_amount), 0) AS total_net
            FROM transactions WHERE {column} = ?
            """,
            (value,),
        )
        return rows_to_dicts([row])[0] if row else {}


class TransactionStatusHistoryRepository(BaseRepository):
    table = "transaction_status_history"
    model = TransactionStatusHistory
    default_order = "created_at ASC, id ASC"
    has_updated_at = False

    def log(self, transaction_id, from_status, to_status, user_id=None, remarks=None):
        return self.insert(
            {
                "transaction_id": transaction_id,
                "from_status": from_status,
                "to_status": to_status,
                "changed_by_user_id": user_id,
                "remarks": remarks,
                "created_at": utcnow(),
            }
        )

    def for_transaction(self, transaction_id):
        rows = db.query_all(
            """
            SELECT h.*, u.name AS changed_by_name, u.role AS changed_by_role
            FROM transaction_status_history h
            LEFT JOIN users u ON u.id = h.changed_by_user_id
            WHERE h.transaction_id = ?
            ORDER BY h.created_at ASC, h.id ASC
            """,
            (transaction_id,),
        )
        return rows_to_dicts(rows)


class PaymentRepository(BaseRepository):
    table = "payments"
    model = Payment
    sortable_columns = ("id", "created_at", "amount", "due_date")
    default_order = "created_at DESC"

    def for_transaction(self, transaction_id):
        return self.find_where(Filter().eq("transaction_id", transaction_id), order_by="id ASC")

    def total_paid(self, transaction_id):
        return float(
            db.query_scalar(
                "SELECT COALESCE(SUM(amount), 0) AS s FROM payments "
                "WHERE transaction_id = ? AND status = 'PAID'",
                (transaction_id,),
                0,
            )
            or 0
        )

    def overdue_for_buyer(self, buyer_id, today):
        """Unpaid dues past their date - the raw signal behind payment reliability."""
        rows = db.query_all(
            """
            SELECT p.*, t.transaction_code
            FROM payments p
            JOIN transactions t ON t.id = p.transaction_id
            WHERE t.buyer_id = ? AND p.status IN ('PENDING', 'PARTIAL')
              AND p.due_date IS NOT NULL AND p.due_date < ?
            """,
            (buyer_id, today),
        )
        return rows_to_dicts(rows)

    def payment_punctuality(self, buyer_id):
        """
        Share of this buyer's settled payments that landed on or before the due date.

        Returns ``None`` when there is nothing to judge, so the caller can say
        "no history" instead of implying a bad record.
        """
        row = db.query_one(
            """
            SELECT COUNT(*) AS settled,
                   SUM(CASE WHEN p.due_date IS NULL OR p.paid_at IS NULL THEN 0
                            WHEN p.paid_at <= p.due_date THEN 1 ELSE 0 END) AS on_time,
                   SUM(CASE WHEN p.due_date IS NOT NULL AND p.paid_at IS NOT NULL THEN 1 ELSE 0 END) AS datable
            FROM payments p
            JOIN transactions t ON t.id = p.transaction_id
            WHERE t.buyer_id = ? AND p.status = 'PAID'
            """,
            (buyer_id,),
        )
        data = rows_to_dicts([row])[0] if row else {}
        datable = int(data.get("datable") or 0)
        if not datable:
            return None
        return round(100.0 * int(data.get("on_time") or 0) / datable, 2)


transaction_repository = TransactionRepository()
transaction_status_history_repository = TransactionStatusHistoryRepository()
payment_repository = PaymentRepository()
