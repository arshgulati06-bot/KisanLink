"""Password hashing and signed access tokens."""
import datetime as dt

import jwt
from werkzeug.security import check_password_hash, generate_password_hash

from app.config.settings import settings
from app.utils.responses import UnauthorizedError


def hash_password(plain_password):
    """Hash a password with a per-user salt (PBKDF2, via Werkzeug)."""
    return generate_password_hash(plain_password)


def verify_password(plain_password, password_hash):
    if not password_hash:
        return False
    try:
        return check_password_hash(password_hash, plain_password)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id, role, extra_claims=None):
    """Issue a signed JWT carrying the user id and role."""
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "user_id": int(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(hours=settings.JWT_EXPIRY_HOURS)).timestamp()),
        "iss": "kisanlink",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token):
    """Validate a token and return its claims, or raise ``UnauthorizedError``."""
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer="kisanlink",
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Your session has expired. Please log in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid authentication token.") from exc


def token_expiry_seconds():
    return settings.JWT_EXPIRY_HOURS * 3600
