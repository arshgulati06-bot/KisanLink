"""
KisanLink — Authentication utilities.
=======================================
Password hashing via werkzeug (already installed).
JWT tokens via stdlib hmac + json — no PyJWT required.

Token format:  base64url(header) . base64url(payload) . base64url(signature)
Algorithm:     HMAC-SHA256
"""
import base64
import hashlib
import hmac
import json
import os
import time
from functools import wraps

from flask import g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

# ------------------------------------------------------------------
# Secret key — read from env; fall back to a fixed development key.
# ------------------------------------------------------------------
_SECRET = os.environ.get(
    "KISANLINK_SECRET_KEY",
    "kisanlink-dev-secret-change-me-in-production-2026",
).encode()

_ALGORITHM = "HS256"
_EXPIRY_HOURS = int(os.environ.get("KISANLINK_JWT_HOURS", "24"))


# ------------------------------------------------------------------
# Password hashing (werkzeug PBKDF2 — safe)
# ------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Return a PBKDF2-SHA256 hash suitable for storing in the database."""
    return generate_password_hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True when *plain* matches *hashed*."""
    if not hashed:
        return False
    try:
        return check_password_hash(hashed, plain)
    except Exception:
        return False


# ------------------------------------------------------------------
# Token helpers (stdlib — no PyJWT)
# ------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(text: str) -> bytes:
    # Add padding
    padding = 4 - len(text) % 4
    if padding != 4:
        text += "=" * padding
    return base64.urlsafe_b64decode(text)


def _sign(header_b64: str, payload_b64: str) -> str:
    msg = f"{header_b64}.{payload_b64}".encode()
    sig = hmac.new(_SECRET, msg, hashlib.sha256).digest()
    return _b64url_encode(sig)


def create_token(user_id: int, role: str) -> str:
    """Issue a signed JWT carrying *user_id* and *role*."""
    now = int(time.time())
    header = {"alg": _ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "role": role,
        "iat": now,
        "exp": now + _EXPIRY_HOURS * 3600,
        "iss": "kisanlink",
    }
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    s = _sign(h, p)
    return f"{h}.{p}.{s}"


def decode_token(token: str) -> dict:
    """
    Validate the token and return its claims.

    Raises :class:`AuthError` if the token is invalid or expired.
    """
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            raise AuthError("Malformed token.")
        h, p, s = parts
        expected = _sign(h, p)
        if not hmac.compare_digest(s, expected):
            raise AuthError("Token signature is invalid.")
        claims = json.loads(_b64url_decode(p))
        if claims.get("exp", 0) < int(time.time()):
            raise AuthError("Your session has expired. Please log in again.")
        if claims.get("iss") != "kisanlink":
            raise AuthError("Token issuer is invalid.")
        return claims
    except AuthError:
        raise
    except Exception:
        raise AuthError("Invalid authentication token.")


# ------------------------------------------------------------------
# Error type
# ------------------------------------------------------------------

class AuthError(Exception):
    """Raised when token validation fails."""
    status_code = 401


# ------------------------------------------------------------------
# Flask helpers
# ------------------------------------------------------------------

def _extract_token() -> str | None:
    """Pull a Bearer token from the Authorization header."""
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return None


def load_current_user():
    """
    Decode the Bearer token and attach the user_id + role to Flask *g*.

    Returns None (and sets nothing) when no token is present.
    Raises :class:`AuthError` when a token is present but invalid.
    """
    token = _extract_token()
    if not token:
        return None
    claims = decode_token(token)  # may raise AuthError
    g.auth_user_id = claims["user_id"]
    g.auth_role = claims["role"]
    return claims


def get_current_user_id() -> int | None:
    return getattr(g, "auth_user_id", None)


def get_current_role() -> str | None:
    return getattr(g, "auth_role", None)


def login_required(view):
    """
    Decorator: reject the request with 401 unless a valid Bearer token is present.

    Sets ``g.auth_user_id`` and ``g.auth_role`` for the view to use.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify({"success": False, "error": "Authentication required."}), 401
        try:
            claims = decode_token(token)
        except AuthError as exc:
            return jsonify({"success": False, "error": str(exc)}), 401
        g.auth_user_id = claims["user_id"]
        g.auth_role = claims["role"]
        return view(*args, **kwargs)
    return wrapper


def require_role(*roles):
    """
    Decorator: like *login_required* but also asserts the user's role.

    Usage::

        @require_role("FARMER", "FPO")
        def create_lot():
            ...
    """
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            role = g.auth_role
            if role not in roles:
                return (
                    jsonify({"success": False, "error": f"Access denied. Requires role: {', '.join(roles)}."}),
                    403,
                )
            return view(*args, **kwargs)
        return wrapper
    return decorator
