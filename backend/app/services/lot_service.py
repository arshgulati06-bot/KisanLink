"""
Lot lifecycle: create, list, publish, withdraw.

A lot is the farmer's unit of supply. Everything downstream - intelligence,
matching, offers, transactions - hangs off one.
"""
import datetime as dt

from app.models.lot import CANCELLED, DRAFT, LISTED, OPEN_STATUSES, SOLD, STATUSES
from app.models.user import ADMIN, FPO
from app.repositories.crop_repository import crop_repository
from app.repositories.lot_repository import lot_contribution_repository, lot_repository
from app.repositories.offer_repository import offer_repository
from app.repositories.user_repository import farmer_profile_repository, fpo_profile_repository
from app.utils.responses import ConflictError, ForbiddenError, NotFoundError, ValidationError


def create_lot(user, data):
    """
    Create a lot for the signed-in farmer or FPO.

    Location falls back to the seller's profile, so a farmer who already gave
    their village at signup does not have to repeat it for every lot.
    """
    crop = crop_repository.find_by_id(data["crop_id"])
    if not crop:
        raise NotFoundError("Crop not found.")
    if not crop.is_active:
        raise ValidationError(f"'{crop.name}' is no longer available for listing.")

    grade = (data.get("grade") or "B").upper()
    if grade not in crop.grades:
        raise ValidationError(
            f"'grade' must be one of {', '.join(crop.grades)} for {crop.name}."
        )

    payload = dict(data)
    payload.update(
        {
            "lot_code": lot_repository.next_code(),
            "seller_user_id": user.id,
            "seller_type": FPO if user.role == FPO else "FARMER",
            "grade": grade,
            "unit": (data.get("unit") or crop.default_unit).upper(),
            "status": DRAFT,
        }
    )
    _apply_seller_location(user, payload)
    _validate_dates(payload)

    if user.role == FPO:
        fpo = fpo_profile_repository.find_by_user_id(user.id)
        if fpo:
            payload["fpo_id"] = fpo.id

    lot_id = lot_repository.insert(payload)
    return lot_repository.detail(lot_id)


def _apply_seller_location(user, payload):
    """Fill missing location fields from the seller's profile."""
    if payload.get("district") and payload.get("latitude") is not None:
        return
    profile = (
        fpo_profile_repository.find_by_user_id(user.id)
        if user.role == FPO
        else farmer_profile_repository.find_by_user_id(user.id)
    )
    if not profile:
        return
    payload.setdefault("district", profile.district)
    payload.setdefault("state", profile.state)
    if payload.get("latitude") is None:
        payload["latitude"] = profile.latitude
        payload["longitude"] = profile.longitude
    if hasattr(profile, "village"):
        payload.setdefault("village", profile.village)


def _validate_dates(payload):
    harvest = payload.get("harvest_date")
    available_from = payload.get("available_from")
    available_until = payload.get("available_until")
    if available_from and available_until and str(available_from) > str(available_until):
        raise ValidationError("'available_until' must be on or after 'available_from'.")
    if harvest and available_until and str(harvest) > str(available_until):
        raise ValidationError("'available_until' cannot be before the harvest date.")


def get_lot(lot_id):
    lot = lot_repository.find_by_id(lot_id)
    if not lot:
        raise NotFoundError("Lot not found.")
    return lot


def get_lot_detail(lot_id, include_offers=False, viewer=None):
    """Full lot view for a detail page."""
    detail = lot_repository.detail(lot_id)
    if not detail:
        raise NotFoundError("Lot not found.")
    if detail.get("is_aggregated"):
        detail["contributions"] = lot_contribution_repository.detailed_for_lot(lot_id)
    if include_offers:
        detail["offers"] = offer_repository.live_offers_for_lot(lot_id)
    if viewer is not None:
        detail["is_owner"] = detail["seller_user_id"] == viewer.id
    return detail


def list_lots(viewer=None, mine=False, **filters):
    """
    List lots.

    ``mine=True`` scopes to the caller's own lots (the farmer dashboard).
    Otherwise only open lots are listed, because a buyer has no business
    browsing another farmer's drafts.
    """
    if mine:
        if viewer is None:
            raise ForbiddenError("Sign in to view your own lots.")
        filters["seller_user_id"] = viewer.id
    elif viewer is None or viewer.role != ADMIN:
        filters.setdefault("statuses", list(OPEN_STATUSES))
    return lot_repository.search(**filters)


def update_lot(user, lot_id, data):
    """
    Edit a lot.

    Once a buyer has made an offer, the commercial terms are frozen: changing
    the quantity or grade under a live offer would let a seller move the goal
    posts after a buyer committed to a price.
    """
    lot = get_lot(lot_id)
    _assert_owner(user, lot)
    if lot.status in (SOLD, CANCELLED):
        raise ConflictError(f"A {lot.status.lower()} lot can no longer be edited.")

    locked_fields = {"quantity", "grade", "crop_id", "unit"}
    if offer_repository.count_for_lot(lot_id, statuses=["PENDING", "COUNTERED"]):
        changing = locked_fields & set(data.keys())
        if changing:
            raise ConflictError(
                "This lot has live offers, so "
                f"{', '.join(sorted(changing))} cannot be changed. "
                "Withdraw or reject the offers first."
            )

    if "grade" in data:
        crop = crop_repository.find_by_id(lot.crop_id)
        grade = data["grade"].upper()
        if crop and grade not in crop.grades:
            raise ValidationError(f"'grade' must be one of {', '.join(crop.grades)}.")
        data["grade"] = grade

    payload = {**lot.to_dict(), **data}
    _validate_dates(payload)
    lot_repository.update(lot_id, data)
    return lot_repository.detail(lot_id)


def publish_lot(user, lot_id):
    """Move a draft lot to LISTED so buyers and matching can see it."""
    lot = get_lot(lot_id)
    _assert_owner(user, lot)
    if lot.status == LISTED:
        return lot_repository.detail(lot_id)
    if lot.status != DRAFT:
        raise ConflictError(f"A {lot.status.lower()} lot cannot be published.")
    missing = [
        field
        for field in ("quantity", "grade", "crop_id")
        if getattr(lot, field, None) in (None, "")
    ]
    if missing:
        raise ValidationError(
            "Complete the lot before publishing.",
            details={field: f"'{field}' is required to publish." for field in missing},
        )
    lot_repository.set_status(lot_id, LISTED)
    return lot_repository.detail(lot_id)


def withdraw_lot(user, lot_id, reason=None):
    """Cancel a lot and reject any offers still standing against it."""
    lot = get_lot(lot_id)
    _assert_owner(user, lot)
    if lot.status == SOLD:
        raise ConflictError("A sold lot cannot be withdrawn.")
    lot_repository.update(lot_id, {"status": CANCELLED, "notes": reason or lot.notes})
    offer_repository.reject_other_offers(lot_id, accepted_offer_id=0)
    return lot_repository.detail(lot_id)


def delete_lot(user, lot_id):
    """
    Delete a lot outright.

    Only allowed while it is a draft nobody has seen; anything further along is
    part of a record other people rely on.
    """
    lot = get_lot(lot_id)
    _assert_owner(user, lot)
    if lot.status != DRAFT:
        raise ConflictError(
            "Only draft lots can be deleted. Withdraw the lot instead so the record is kept."
        )
    lot_repository.delete(lot_id)
    return True


def set_status(user, lot_id, status):
    lot = get_lot(lot_id)
    _assert_owner(user, lot)
    status = status.upper()
    if status not in STATUSES:
        raise ValidationError(f"'status' must be one of: {', '.join(STATUSES)}.")
    lot_repository.set_status(lot_id, status)
    return lot_repository.detail(lot_id)


def seller_dashboard(user):
    """Header counts plus the lots that currently need attention."""
    summary = lot_repository.seller_summary(user.id)
    lots, _ = lot_repository.search(
        seller_user_id=user.id, statuses=list(OPEN_STATUSES), page_size=5
    )
    return {
        "summary": summary,
        "active_lots": lots,
        "pending_offers": offer_repository.search(
            seller_user_id=user.id, status="PENDING", page_size=5
        )[0],
    }


def expire_stale_lots():
    """Housekeeping: close out lots whose availability window has passed."""
    return lot_repository.expire_stale(dt.date.today().isoformat())


def _assert_owner(user, lot):
    if user.role == ADMIN or lot.seller_user_id == user.id:
        return
    raise ForbiddenError("You can only manage your own lots.")
