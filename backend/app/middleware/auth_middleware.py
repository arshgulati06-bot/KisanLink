"""
Authentication.

``@login_required`` reads the Bearer token, loads the user once per request and
puts them on Flask's ``g`` so controllers can call ``current_user()`` without
touching the database again.
"""
from functools import wraps

from flask import g, request

from app.repositories.user_repository import user_repository
from app.utils.responses import UnauthorizedError
from app.utils.security import decode_access_token


def _extract_token():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    # Accepted as a convenience for browser testing; the header is preferred.
    return request.args.get("access_token")


def load_user_from_token(required=True):
    """Resolve the caller, or raise when a token is required and absent/bad."""
    token = _extract_token()
    if not token:
        if required:
            raise UnauthorizedError("Authentication required. Send a Bearer token.")
        return None

    claims = decode_access_token(token)
    user = user_repository.find_by_id(claims.get("user_id"))
    if not user:
        raise UnauthorizedError("The account for this token no longer exists.")
    if not user.is_active:
        raise UnauthorizedError("This account has been deactivated.")
    g.current_user = user
    g.token_claims = claims
    return user


def login_required(view):
    """Reject the request unless a valid token is present."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        load_user_from_token(required=True)
        return view(*args, **kwargs)

    return wrapper


def optional_login(view):
    """
    Load the user when a token is present, but allow anonymous access.

    Used on public listings that show a little more to a signed-in caller.
    """

    @wraps(view)
    def wrapper(*args, **kwargs):
        try:
            load_user_from_token(required=False)
        except UnauthorizedError:
            g.current_user = None
        return view(*args, **kwargs)

    return wrapper


def current_user():
    """The signed-in user for this request, or ``None``."""
    return getattr(g, "current_user", None)


def require_current_user():
    user = current_user()
    if user is None:
        raise UnauthorizedError("Authentication required.")
    return user
