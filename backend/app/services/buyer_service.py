"""Buyer profiles and buyer demand (requirements)."""
import datetime as dt

from app.models.buyer_profile import BUYER_TYPES
from app.models.buyer_requirement import ACTIVE_STATUSES, CLOSED, STATUSES
from app.models.user import ADMIN
from app.repositories.buyer_repository import buyer_requirement_repository
from app.repositories.crop_repository import crop_repository
from app.repositories.user_repository import buyer_profile_repository
from app.utils.responses import ConflictError, ForbiddenError, NotFoundError, ValidationError


# ---------------------------------------------------------------------------
# Buyer profiles
# ---------------------------------------------------------------------------
def list_buyers(buyer_type=None, verification_status=None, district=None, query=None,
                page=1, page_size=20, order_by=None):
    buyers, total = buyer_profile_repository.search(
        buyer_type=buyer_type,
        verification_status=verification_status,
        district=district,
        query=query,
        page=page,
        page_size=page_size,
        order_by=order_by,
    )
    return [buyer.to_dict() for buyer in buyers], total


def get_buyer(buyer_id):
    buyer = buyer_profile_repository.find_by_id(buyer_id)
    if not buyer:
        raise NotFoundError("Buyer not found.")
    return buyer


def get_buyer_detail(buyer_id):
    """Public buyer card: who they are, what they buy, how reliable they look."""
    detail = buyer_profile_repository.profile_with_contact(buyer_id)
    if not detail:
        raise NotFoundError("Buyer not found.")
    requirements, _ = buyer_requirement_repository.search(
        buyer_id=buyer_id, active_only=True, page_size=10
    )
    detail["active_requirements"] = requirements
    detail["summary"] = buyer_requirement_repository.buyer_summary(buyer_id)
    detail["verification_disclaimer"] = (
        "Verification status reflects a KisanLink platform review only. "
        "It is not a government KYC or GST verification."
    )
    return detail


def save_buyer_profile(user, data):
    """Create or update the signed-in buyer's own profile."""
    if data.get("buyer_type"):
        buyer_type = data["buyer_type"].upper()
        if buyer_type not in BUYER_TYPES:
            raise ValidationError(f"'buyer_type' must be one of: {', '.join(BUYER_TYPES)}.")
        data["buyer_type"] = buyer_type
    # Verification is never self-serve; it is set through the trust service.
    data.pop("verification_status", None)
    data.pop("trust_score", None)
    data.pop("is_seed_data", None)
    profile = buyer_profile_repository.upsert(user.id, data)
    return profile.to_dict()


# ---------------------------------------------------------------------------
# Buyer demand
# ---------------------------------------------------------------------------
def create_requirement(user, data):
    """Record what this buyer wants to buy."""
    buyer = _require_own_buyer_profile(user)
    crop = crop_repository.find_by_id(data["crop_id"])
    if not crop:
        raise NotFoundError("Crop not found.")

    minimum, maximum = data.get("price_min"), data.get("price_max")
    if minimum is not None and maximum is not None and float(minimum) > float(maximum):
        raise ValidationError("'price_min' cannot be greater than 'price_max'.")

    valid_from, valid_until = data.get("valid_from"), data.get("valid_until")
    if valid_from and valid_until and str(valid_from) > str(valid_until):
        raise ValidationError("'valid_until' must be on or after 'valid_from'.")

    grade = (data.get("min_grade") or "C").upper()
    if grade not in crop.grades:
        raise ValidationError(f"'min_grade' must be one of {', '.join(crop.grades)}.")

    payload = dict(data)
    payload.update(
        {
            "buyer_id": buyer.id,
            "min_grade": grade,
            "unit": (data.get("unit") or crop.default_unit).upper(),
            "status": "OPEN",
            "fulfilled_quantity": 0,
        }
    )
    payload.setdefault("delivery_district", buyer.district)
    payload.setdefault("delivery_state", buyer.state)
    if payload.get("latitude") is None:
        payload["latitude"] = buyer.latitude
        payload["longitude"] = buyer.longitude

    requirement_id = buyer_requirement_repository.insert(payload)
    return buyer_requirement_repository.detail(requirement_id)


def get_requirement(requirement_id):
    requirement = buyer_requirement_repository.find_by_id(requirement_id)
    if not requirement:
        raise NotFoundError("Buyer requirement not found.")
    return requirement


def get_requirement_detail(requirement_id):
    detail = buyer_requirement_repository.detail(requirement_id)
    if not detail:
        raise NotFoundError("Buyer requirement not found.")
    return detail


def list_requirements(viewer=None, mine=False, **filters):
    if mine:
        buyer = _require_own_buyer_profile(viewer)
        filters["buyer_id"] = buyer.id
    else:
        filters.setdefault("active_only", True)
    return buyer_requirement_repository.search(**filters)


def update_requirement(user, requirement_id, data):
    requirement = get_requirement(requirement_id)
    _assert_owner(user, requirement)
    if requirement.status in ("FULFILLED", "CLOSED"):
        raise ConflictError(f"A {requirement.status.lower()} requirement cannot be edited.")

    if float(data.get("required_quantity", requirement.required_quantity)) < float(
        requirement.fulfilled_quantity or 0
    ):
        raise ValidationError(
            "'required_quantity' cannot be less than the quantity already committed "
            f"({float(requirement.fulfilled_quantity or 0):,.2f})."
        )
    minimum = data.get("price_min", requirement.price_min)
    maximum = data.get("price_max", requirement.price_max)
    if minimum is not None and maximum is not None and float(minimum) > float(maximum):
        raise ValidationError("'price_min' cannot be greater than 'price_max'.")

    data.pop("fulfilled_quantity", None)
    buyer_requirement_repository.update(requirement_id, data)
    return buyer_requirement_repository.detail(requirement_id)


def close_requirement(user, requirement_id):
    requirement = get_requirement(requirement_id)
    _assert_owner(user, requirement)
    buyer_requirement_repository.update(requirement_id, {"status": CLOSED})
    return buyer_requirement_repository.detail(requirement_id)


def set_requirement_status(user, requirement_id, status):
    requirement = get_requirement(requirement_id)
    _assert_owner(user, requirement)
    status = status.upper()
    if status not in STATUSES:
        raise ValidationError(f"'status' must be one of: {', '.join(STATUSES)}.")
    buyer_requirement_repository.update(requirement_id, {"status": status})
    return buyer_requirement_repository.detail(requirement_id)


def buyer_dashboard(user):
    """Buyer-side landing data: open demand and how it is being met."""
    buyer = _require_own_buyer_profile(user)
    requirements, _ = buyer_requirement_repository.search(
        buyer_id=buyer.id, statuses=list(ACTIVE_STATUSES), page_size=5
    )
    from app.repositories.offer_repository import offer_repository
    from app.repositories.transaction_repository import transaction_repository

    return {
        "buyer": buyer.to_dict(),
        "summary": buyer_requirement_repository.buyer_summary(buyer.id),
        "active_requirements": requirements,
        "pending_offers": offer_repository.search(
            buyer_id=buyer.id, status="PENDING", page_size=5
        )[0],
        "transactions": transaction_repository.party_summary(buyer_id=buyer.id),
    }


def expire_stale_requirements():
    return buyer_requirement_repository.expire_stale(dt.date.today().isoformat())


def _require_own_buyer_profile(user):
    if user is None:
        raise ForbiddenError("Sign in as a buyer to continue.")
    profile = buyer_profile_repository.find_by_user_id(user.id)
    if not profile:
        raise NotFoundError(
            "No buyer profile found for this account. Create your buyer profile first."
        )
    return profile


def _assert_owner(user, requirement):
    if user.role == ADMIN:
        return
    buyer = buyer_profile_repository.find_by_user_id(user.id)
    if not buyer or buyer.id != requirement.buyer_id:
        raise ForbiddenError("You can only manage your own buyer requirements.")
