"""
KisanLink — Sale Lot repository.
==================================
All SQL for the lots, buyer_requirements, offers, and transactions tables.
"""
import datetime
import random
import string

import kl_db as db


def _utcnow():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _tx_code():
    """Generate a short, unique-ish transaction code like KL-2026-A4B7."""
    year = datetime.datetime.now().year
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"KL-{year}-{suffix}"


# ------------------------------------------------------------------
# Lots
# ------------------------------------------------------------------

def create_lot(farmer_user_id: int, data: dict) -> int:
    """Insert a new sale lot and return its id."""
    allowed = {
        "commodity", "variety", "grade", "quantity_qtl", "expected_price",
        "district", "state", "market", "harvest_date", "notes",
        "has_forecast", "forecast_sale_day", "forecast_price_p50",
    }
    payload = {k: v for k, v in data.items() if k in allowed and v is not None}
    payload["farmer_user_id"] = farmer_user_id
    payload.setdefault("grade", "Grade A")
    payload.setdefault("status", "AVAILABLE")
    payload.setdefault("has_forecast", 0)
    payload["created_at"] = _utcnow()
    payload["updated_at"] = _utcnow()
    columns = ", ".join(payload.keys())
    placeholders = ", ".join("?" for _ in payload)
    return db.execute(
        f"INSERT INTO lots ({columns}) VALUES ({placeholders})",
        list(payload.values()),
    )


def get_lot_by_id(lot_id: int) -> dict | None:
    return db.query_one("SELECT * FROM lots WHERE id = ?", (lot_id,))


def get_lots_by_farmer(farmer_user_id: int) -> list[dict]:
    return db.query_all(
        "SELECT * FROM lots WHERE farmer_user_id = ? ORDER BY created_at DESC",
        (farmer_user_id,),
    )


def get_available_lots(commodity: str | None = None, limit: int = 50) -> list[dict]:
    """Return AVAILABLE lots, optionally filtered by commodity."""
    if commodity:
        return db.query_all(
            "SELECT * FROM lots WHERE status = 'AVAILABLE' AND LOWER(commodity) = ? ORDER BY created_at DESC LIMIT ?",
            (commodity.lower(), limit),
        )
    return db.query_all(
        "SELECT * FROM lots WHERE status = 'AVAILABLE' ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )


def update_lot_status(lot_id: int, status: str) -> bool:
    db.execute(
        "UPDATE lots SET status = ?, updated_at = ? WHERE id = ?",
        (status, _utcnow(), lot_id),
    )
    return True


# ------------------------------------------------------------------
# Buyer requirements
# ------------------------------------------------------------------

def create_buyer_requirement(buyer_user_id: int, data: dict) -> int:
    allowed = {
        "commodity", "grade", "quantity_qtl_min", "quantity_qtl_max",
        "price_per_qtl", "preferred_state", "preferred_district", "valid_until", "notes",
    }
    payload = {k: v for k, v in data.items() if k in allowed and v is not None}
    payload["buyer_user_id"] = buyer_user_id
    payload.setdefault("grade", "Grade A")
    payload.setdefault("status", "OPEN")
    payload.setdefault("quantity_qtl_min", 10)
    payload["created_at"] = _utcnow()
    payload["updated_at"] = _utcnow()
    columns = ", ".join(payload.keys())
    placeholders = ", ".join("?" for _ in payload)
    return db.execute(
        f"INSERT INTO buyer_requirements ({columns}) VALUES ({placeholders})",
        list(payload.values()),
    )


def get_requirements_by_buyer(buyer_user_id: int) -> list[dict]:
    return db.query_all(
        "SELECT * FROM buyer_requirements WHERE buyer_user_id = ? ORDER BY created_at DESC",
        (buyer_user_id,),
    )


def get_open_requirements(commodity: str | None = None) -> list[dict]:
    if commodity:
        return db.query_all(
            "SELECT * FROM buyer_requirements WHERE status = 'OPEN' AND LOWER(commodity) = ? ORDER BY created_at DESC",
            (commodity.lower(),),
        )
    return db.query_all(
        "SELECT * FROM buyer_requirements WHERE status = 'OPEN' ORDER BY created_at DESC LIMIT 50",
        (),
    )


# ------------------------------------------------------------------
# Offers
# ------------------------------------------------------------------

def get_requirement_by_id(requirement_id: int) -> dict | None:
    return db.query_one(
        "SELECT * FROM buyer_requirements WHERE id = ?", (requirement_id,)
    )


def create_offer(buyer_user_id: int, seller_user_id: int, lot_id: int, data: dict,
                 initiated_by: str = "BUYER") -> int:
    payload = {
        "lot_id": lot_id,
        "requirement_id": data.get("requirement_id"),
        "buyer_user_id": buyer_user_id,
        "seller_user_id": seller_user_id,
        "price_per_qtl": float(data["price_per_qtl"]),
        "quantity_qtl": float(data["quantity_qtl"]),
        "status": "PENDING",
        "initiated_by": "FARMER" if initiated_by == "FARMER" else "BUYER",
        "message": data.get("message"),
        "created_at": _utcnow(),
        "updated_at": _utcnow(),
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    columns = ", ".join(payload.keys())
    placeholders = ", ".join("?" for _ in payload)
    return db.execute(
        f"INSERT INTO offers ({columns}) VALUES ({placeholders})",
        list(payload.values()),
    )


def get_offers_for_lot(lot_id: int) -> list[dict]:
    return db.query_all(
        "SELECT * FROM offers WHERE lot_id = ? ORDER BY created_at DESC",
        (lot_id,),
    )


def get_offers_for_seller(seller_user_id: int) -> list[dict]:
    return db.query_all(
        "SELECT * FROM offers WHERE seller_user_id = ? ORDER BY created_at DESC LIMIT 50",
        (seller_user_id,),
    )


def get_offers_by_buyer(buyer_user_id: int) -> list[dict]:
    return db.query_all(
        "SELECT * FROM offers WHERE buyer_user_id = ? ORDER BY created_at DESC LIMIT 50",
        (buyer_user_id,),
    )


def respond_to_offer(offer_id: int, status: str) -> bool:
    """Accept, reject, or counter an offer."""
    valid = {"ACCEPTED", "REJECTED", "COUNTERED", "WITHDRAWN"}
    if status.upper() not in valid:
        return False
    db.execute(
        "UPDATE offers SET status = ?, responded_at = ?, updated_at = ? WHERE id = ?",
        (status.upper(), _utcnow(), _utcnow(), offer_id),
    )
    return True


# ------------------------------------------------------------------
# Transactions
# ------------------------------------------------------------------

def create_transaction_from_offer(offer_id: int) -> dict | None:
    """Create a transaction when an offer is accepted. Returns the new transaction row."""
    offer = db.query_one("SELECT * FROM offers WHERE id = ?", (offer_id,))
    if not offer:
        return None
    lot = db.query_one("SELECT * FROM lots WHERE id = ?", (offer["lot_id"],))
    if not lot:
        return None

    gross = offer["price_per_qtl"] * offer["quantity_qtl"]
    payload = {
        "transaction_code": _tx_code(),
        "offer_id": offer_id,
        "lot_id": offer["lot_id"],
        "buyer_user_id": offer["buyer_user_id"],
        "seller_user_id": offer["seller_user_id"],
        "commodity": lot["commodity"],
        "quantity_qtl": offer["quantity_qtl"],
        "price_per_qtl": offer["price_per_qtl"],
        "gross_amount": gross,
        "transport_cost": 0,
        "net_amount": gross,
        "status": "ACCEPTED",
        "created_at": _utcnow(),
        "updated_at": _utcnow(),
    }
    tx_id = db.execute(
        """INSERT INTO transactions
           (transaction_code, offer_id, lot_id, buyer_user_id, seller_user_id,
            commodity, quantity_qtl, price_per_qtl, gross_amount, transport_cost, net_amount,
            status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [payload[k] for k in (
            "transaction_code", "offer_id", "lot_id", "buyer_user_id", "seller_user_id",
            "commodity", "quantity_qtl", "price_per_qtl", "gross_amount", "transport_cost",
            "net_amount", "status", "created_at", "updated_at",
        )],
    )
    return db.query_one("SELECT * FROM transactions WHERE id = ?", (tx_id,))


def get_transactions_for_user(user_id: int) -> list[dict]:
    return db.query_all(
        """SELECT * FROM transactions
           WHERE seller_user_id = ? OR buyer_user_id = ?
           ORDER BY created_at DESC LIMIT 50""",
        (user_id, user_id),
    )
