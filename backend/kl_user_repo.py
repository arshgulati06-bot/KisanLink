"""
KisanLink — User and profile repositories.
==========================================
All SQL for users, farmer_profiles, and buyer_profiles lives here.
Controllers call these functions; no SQL appears in app.py or elsewhere.
"""
import datetime

import kl_db as db
from kl_auth import hash_password


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _utcnow():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------
# Users
# ------------------------------------------------------------------

def find_user_by_id(user_id: int) -> dict | None:
    return db.query_one("SELECT * FROM users WHERE id = ?", (user_id,))


def find_user_by_username(username: str) -> dict | None:
    return db.query_one("SELECT * FROM users WHERE username = ?", (username.strip().lower(),))


def find_user_by_phone(phone: str) -> dict | None:
    return db.query_one("SELECT * FROM users WHERE phone = ?", (phone,))


def username_taken(username: str, exclude_id: int | None = None) -> bool:
    uname = username.strip().lower()
    if exclude_id is not None:
        row = db.query_one(
            "SELECT id FROM users WHERE username = ? AND id <> ?", (uname, exclude_id)
        )
    else:
        row = db.query_one("SELECT id FROM users WHERE username = ?", (uname,))
    return row is not None


def phone_taken(phone: str, exclude_id: int | None = None) -> bool:
    if not phone:
        return False
    if exclude_id is not None:
        row = db.query_one(
            "SELECT id FROM users WHERE phone = ? AND id <> ?", (phone, exclude_id)
        )
    else:
        row = db.query_one("SELECT id FROM users WHERE phone = ?", (phone,))
    return row is not None


def email_taken(email: str, exclude_id: int | None = None) -> bool:
    if not email:
        return False
    if exclude_id is not None:
        row = db.query_one(
            "SELECT id FROM users WHERE email = ? AND id <> ?", (email, exclude_id)
        )
    else:
        row = db.query_one("SELECT id FROM users WHERE email = ?", (email,))
    return row is not None


def create_user(
    name: str,
    username: str,
    password: str,
    role: str,
    phone: str | None = None,
    email: str | None = None,
    language: str = "en",
) -> int:
    """
    Insert a new user row and return the new id.

    Raises ``ValueError`` when the username is already taken.
    username is stored lowercase for case-insensitive login.
    """
    role = role.upper()
    if role not in ("FARMER", "FPO", "BUYER", "ADMIN"):
        raise ValueError(f"Invalid role: {role!r}")

    uname = username.strip().lower()
    if not uname:
        raise ValueError("username is required.")
    if username_taken(uname):
        raise ValueError("That username is already taken. Please choose another.")
    if phone and phone_taken(phone):
        raise ValueError("An account with this mobile number already exists.")
    if email and email_taken(email):
        raise ValueError("An account with this email address already exists.")

    return db.execute(
        """
        INSERT INTO users (name, username, phone, email, password_hash, role, language, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (name, uname, phone or None, email or None, hash_password(password), role, language, _utcnow(), _utcnow()),
    )


def update_user(user_id: int, data: dict) -> bool:
    """Update allowed fields on the user row.  Returns True on success."""
    allowed = {"name", "email", "language", "password_hash", "username"}
    payload = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not payload:
        return False
    payload["updated_at"] = _utcnow()
    assignments = ", ".join(f"{k} = ?" for k in payload)
    db.execute(
        f"UPDATE users SET {assignments} WHERE id = ?",
        list(payload.values()) + [user_id],
    )
    return True


def safe_user_dict(user: dict) -> dict:
    """Return a user dict with the password_hash removed."""
    if user is None:
        return None
    return {k: v for k, v in user.items() if k != "password_hash"}


# ------------------------------------------------------------------
# Farmer profiles
# ------------------------------------------------------------------

def get_farmer_profile(user_id: int) -> dict | None:
    return db.query_one("SELECT * FROM farmer_profiles WHERE user_id = ?", (user_id,))


def upsert_farmer_profile(user_id: int, data: dict) -> dict:
    """Create or update the farmer profile for *user_id*."""
    allowed = {
        "village", "district", "state", "pincode",
        "land_size_acres", "primary_crops",
    }
    payload = {k: v for k, v in data.items() if k in allowed and v is not None}

    existing = get_farmer_profile(user_id)
    if existing:
        if payload:
            payload["updated_at"] = _utcnow()
            assignments = ", ".join(f"{k} = ?" for k in payload)
            db.execute(
                f"UPDATE farmer_profiles SET {assignments} WHERE user_id = ?",
                list(payload.values()) + [user_id],
            )
    else:
        payload["user_id"] = user_id
        payload.setdefault("state", "Maharashtra")
        payload["created_at"] = _utcnow()
        payload["updated_at"] = _utcnow()
        columns = ", ".join(payload.keys())
        placeholders = ", ".join("?" for _ in payload)
        db.execute(
            f"INSERT INTO farmer_profiles ({columns}) VALUES ({placeholders})",
            list(payload.values()),
        )
    return get_farmer_profile(user_id)


# ------------------------------------------------------------------
# Buyer profiles
# ------------------------------------------------------------------

def get_buyer_profile(user_id: int) -> dict | None:
    return db.query_one("SELECT * FROM buyer_profiles WHERE user_id = ?", (user_id,))


def upsert_buyer_profile(user_id: int, data: dict) -> dict:
    """Create or update the buyer profile for *user_id*."""
    allowed = {
        "business_name", "buyer_type", "gst_number",
        "address", "district", "state", "verification_status", "trust_score",
    }
    payload = {k: v for k, v in data.items() if k in allowed and v is not None}

    existing = get_buyer_profile(user_id)
    if existing:
        if payload:
            payload["updated_at"] = _utcnow()
            assignments = ", ".join(f"{k} = ?" for k in payload)
            db.execute(
                f"UPDATE buyer_profiles SET {assignments} WHERE user_id = ?",
                list(payload.values()) + [user_id],
            )
    else:
        payload["user_id"] = user_id
        payload.setdefault("business_name", "Buyer Business")
        payload.setdefault("buyer_type", "TRADER")
        payload.setdefault("verification_status", "UNVERIFIED")
        payload.setdefault("trust_score", 40.0)
        payload.setdefault("state", "Maharashtra")
        payload["created_at"] = _utcnow()
        payload["updated_at"] = _utcnow()
        columns = ", ".join(payload.keys())
        placeholders = ", ".join("?" for _ in payload)
        db.execute(
            f"INSERT INTO buyer_profiles ({columns}) VALUES ({placeholders})",
            list(payload.values()),
        )
    return get_buyer_profile(user_id)
