"""
Authorisation by role.

Role checks answer "may this kind of account use this endpoint at all". Checks
about a *specific* record - is this your lot, are you a party to this deal -
belong in the services, where the record is actually loaded.
"""
from functools import wraps

from app.middleware.auth_middleware import load_user_from_token
from app.models.user import ADMIN, BUYER, FARMER, FPO, SELLER_ROLES
from app.utils.responses import ForbiddenError


def roles_required(*roles):
    """Allow only the listed roles. Administrators always pass."""
    allowed = {role.upper() for role in roles}

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = load_user_from_token(required=True)
            if user.role != ADMIN and user.role not in allowed:
                raise ForbiddenError(
                    "This action is available to "
                    f"{', '.join(sorted(allowed)).lower()} accounts only."
                )
            return view(*args, **kwargs)

        return wrapper

    return decorator


def farmer_required(view):
    return roles_required(FARMER)(view)


def buyer_required(view):
    return roles_required(BUYER)(view)


def fpo_required(view):
    return roles_required(FPO)(view)


def seller_required(view):
    """Farmers and FPOs both sell, so both may manage lots."""
    return roles_required(*SELLER_ROLES)(view)


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = load_user_from_token(required=True)
        if user.role != ADMIN:
            raise ForbiddenError("This action is restricted to administrators.")
        return view(*args, **kwargs)

    return wrapper
