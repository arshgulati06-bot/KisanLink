"""
Farmer Producer Organisation support.

The problem statement asks for stronger FPO aggregation. The prototype keeps
that deliberately simple and aggregation-*ready*: members are recorded, and
several member lots of the same crop can be pooled into one larger lot that
carries a contribution record for each farmer, so the payout can be split
fairly when the deal settles.

What it is not: a cooperative management system. That is out of scope, and
building half of one would be worse than building none.
"""
from app.models.fpo_member import ACTIVE, MEMBER_ROLES, MEMBER_STATUSES
from app.models.lot import DRAFT, LISTED
from app.models.user import ADMIN, FPO
from app.repositories.crop_repository import crop_repository
from app.repositories.fpo_repository import fpo_member_repository
from app.repositories.lot_repository import lot_contribution_repository, lot_repository
from app.repositories.user_repository import (
    farmer_profile_repository,
    fpo_profile_repository,
    user_repository,
)
from app.utils.responses import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.utils.units import convert_quantity, is_convertible


def save_profile(user, data):
    if user.role not in (FPO, ADMIN):
        raise ForbiddenError("Only an FPO account can maintain an FPO profile.")
    profile = fpo_profile_repository.upsert(user.id, data)
    return profile.to_dict()


def get_fpo(fpo_id):
    fpo = fpo_profile_repository.find_by_id(fpo_id)
    if not fpo:
        raise NotFoundError("FPO not found.")
    return fpo


def get_fpo_detail(fpo_id):
    fpo = get_fpo(fpo_id)
    return {
        **fpo.to_dict(),
        "summary": fpo_member_repository.fpo_summary(fpo_id),
        "members": fpo_member_repository.list_members(fpo_id, status=ACTIVE),
    }


def list_fpos(district=None, state=None, page=1, page_size=20, order_by=None):
    from app.repositories import Filter

    filters = Filter().eq("district", district).eq("state", state)
    total = fpo_profile_repository.count_where(filters)
    rows = fpo_profile_repository.find_where(
        filters, order_by=order_by, limit=page_size, offset=(page - 1) * page_size
    )
    return [row.to_dict() for row in rows], total


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------
def add_member(user, fpo_id, data):
    """Enrol a farmer, identified by their mobile number or farmer id."""
    fpo = get_fpo(fpo_id)
    _assert_fpo_owner(user, fpo)

    farmer = _resolve_farmer(data)
    existing = fpo_member_repository.find_membership(fpo_id, farmer.id)
    if existing and existing.status == ACTIVE:
        raise ConflictError("This farmer is already an active member of the FPO.")

    member_role = (data.get("member_role") or "MEMBER").upper()
    if member_role not in MEMBER_ROLES:
        raise ValidationError(f"'member_role' must be one of: {', '.join(MEMBER_ROLES)}.")

    if existing:
        fpo_member_repository.update(
            existing.id, {"status": ACTIVE, "member_role": member_role}
        )
    else:
        fpo_member_repository.insert(
            {
                "fpo_id": fpo_id,
                "farmer_id": farmer.id,
                "member_role": member_role,
                "status": ACTIVE,
            }
        )
    # Keep the farmer's own profile pointing at their FPO, so a lot they create
    # is attributed correctly without them having to say so.
    farmer_profile_repository.update(farmer.id, {"fpo_id": fpo_id})
    fpo_profile_repository.recount_members(fpo_id)
    return fpo_member_repository.list_members(fpo_id)


def _resolve_farmer(data):
    if data.get("farmer_id"):
        farmer = farmer_profile_repository.find_by_id(data["farmer_id"])
        if not farmer:
            raise NotFoundError("Farmer not found.")
        return farmer
    phone = data.get("phone")
    if not phone:
        raise ValidationError("Provide either 'farmer_id' or the farmer's 'phone'.")
    account = user_repository.find_by_phone(phone)
    if not account:
        raise NotFoundError("No account is registered with that mobile number.")
    farmer = farmer_profile_repository.find_by_user_id(account.id)
    if not farmer:
        raise ValidationError("That account is not a farmer account.")
    return farmer


def list_members(fpo_id, status=None):
    get_fpo(fpo_id)
    return fpo_member_repository.list_members(fpo_id, status=status)


def update_member(user, fpo_id, member_id, data):
    fpo = get_fpo(fpo_id)
    _assert_fpo_owner(user, fpo)
    membership = fpo_member_repository.find_by_id(member_id)
    if not membership or membership.fpo_id != fpo_id:
        raise NotFoundError("Membership not found for this FPO.")
    if data.get("status") and data["status"].upper() not in MEMBER_STATUSES:
        raise ValidationError(f"'status' must be one of: {', '.join(MEMBER_STATUSES)}.")
    fpo_member_repository.update(member_id, data)
    fpo_profile_repository.recount_members(fpo_id)
    return fpo_member_repository.list_members(fpo_id)


def remove_member(user, fpo_id, member_id):
    fpo = get_fpo(fpo_id)
    _assert_fpo_owner(user, fpo)
    membership = fpo_member_repository.find_by_id(member_id)
    if not membership or membership.fpo_id != fpo_id:
        raise NotFoundError("Membership not found for this FPO.")
    fpo_member_repository.update(member_id, {"status": "REMOVED"})
    farmer_profile_repository.update(membership.farmer_id, {"fpo_id": None})
    fpo_profile_repository.recount_members(fpo_id)
    return True


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def aggregation_candidates(user, fpo_id, crop_id):
    """Member lots of one crop that are free to be pooled."""
    fpo = get_fpo(fpo_id)
    _assert_fpo_owner(user, fpo)
    rows = fpo_member_repository.aggregation_candidates(fpo_id, crop_id)
    total = sum(float(row.get("quantity") or 0) for row in rows)
    return {
        "fpo_id": fpo_id,
        "crop_id": crop_id,
        "candidate_lots": rows,
        "candidate_count": len(rows),
        "total_quantity": round(total, 2),
        "note": (
            "Only draft or listed member lots with no live offer can be aggregated, "
            "so a lot already under negotiation is never swept into a pool."
        ),
    }


def aggregate_lots(user, fpo_id, data):
    """
    Pool several member lots into one FPO lot.

    The source lots are cancelled and their quantities recorded as
    contributions on the new lot. The aggregate takes the LOWEST grade of its
    inputs, because a pooled consignment can only honestly be sold at the
    quality of its weakest part.
    """
    fpo = get_fpo(fpo_id)
    _assert_fpo_owner(user, fpo)

    lot_ids = data.get("lot_ids") or []
    if len(lot_ids) < 2:
        raise ValidationError("Select at least two lots to aggregate.")

    crop_id = None
    unit = None
    lots = []
    for lot_id in lot_ids:
        lot = lot_repository.find_by_id(lot_id)
        if not lot:
            raise NotFoundError(f"Lot {lot_id} not found.")
        if lot.status not in (DRAFT, LISTED):
            raise ConflictError(
                f"Lot {lot.lot_code} is {lot.status.lower()} and cannot be aggregated."
            )
        if lot.is_aggregated:
            raise ConflictError(f"Lot {lot.lot_code} is already an aggregated lot.")
        crop_id = crop_id or lot.crop_id
        if lot.crop_id != crop_id:
            raise ValidationError("All lots being aggregated must be of the same crop.")
        unit = unit or lot.unit
        if not is_convertible(lot.unit) and lot.unit != unit:
            raise ValidationError(
                f"Lot {lot.lot_code} is measured in {lot.unit}, which cannot be pooled "
                f"with {unit}."
            )
        lots.append(lot)

    crop = crop_repository.find_by_id(crop_id)
    grade_order = crop.grades if crop else ["A", "B", "C"]
    total_quantity = sum(convert_quantity(lot.quantity, lot.unit, unit) for lot in lots)
    lowest_grade = max(lots, key=lambda lot: grade_order.index(lot.grade) if lot.grade in grade_order else 99).grade

    aggregate_id = lot_repository.insert(
        {
            "lot_code": lot_repository.next_code(),
            "seller_user_id": user.id,
            "seller_type": "FPO",
            "fpo_id": fpo_id,
            "crop_id": crop_id,
            "variety": data.get("variety") or lots[0].variety,
            "quantity": round(total_quantity, 2),
            "unit": unit,
            "grade": lowest_grade,
            "expected_price": data.get("expected_price"),
            "harvest_date": min((lot.harvest_date for lot in lots if lot.harvest_date), default=None),
            "available_from": data.get("available_from"),
            "available_until": data.get("available_until"),
            "district": fpo.district or lots[0].district,
            "state": fpo.state or lots[0].state,
            "latitude": fpo.latitude if fpo.latitude is not None else lots[0].latitude,
            "longitude": fpo.longitude if fpo.longitude is not None else lots[0].longitude,
            "status": DRAFT,
            "is_aggregated": 1,
            "notes": (
                f"Aggregated from {len(lots)} member lots. "
                f"Graded {lowest_grade}, the lowest grade among the pooled lots."
            ),
        }
    )

    for lot in lots:
        farmer = farmer_profile_repository.find_by_user_id(lot.seller_user_id)
        lot_contribution_repository.insert(
            {
                "lot_id": aggregate_id,
                "farmer_id": farmer.id if farmer else None,
                "quantity": round(convert_quantity(lot.quantity, lot.unit, unit), 2),
                "grade": lot.grade,
            }
        )
        lot_repository.update(
            lot.id,
            {
                "status": "CANCELLED",
                "notes": f"Pooled into FPO aggregated lot (id {aggregate_id}).",
            },
        )

    return {
        "aggregated_lot": lot_repository.detail(aggregate_id),
        "contributions": lot_contribution_repository.detailed_for_lot(aggregate_id),
        "source_lot_count": len(lots),
    }


def contribution_payouts(fpo_id, lot_id):
    """The per-farmer split for an aggregated lot."""
    lot = lot_repository.find_by_id(lot_id)
    if not lot or lot.fpo_id != fpo_id:
        raise NotFoundError("Aggregated lot not found for this FPO.")
    contributions = lot_contribution_repository.detailed_for_lot(lot_id)
    return {
        "lot": lot.to_dict(),
        "contributions": contributions,
        "total_quantity": lot_contribution_repository.total_quantity(lot_id),
        "payouts_recorded": any(c.get("payout_amount") is not None for c in contributions),
        "note": (
            "Payouts are recorded pro rata by contributed quantity once the "
            "transaction is completed."
        ),
    }


def fpo_dashboard(user):
    fpo = fpo_profile_repository.find_by_user_id(user.id)
    if not fpo:
        raise NotFoundError("No FPO profile found for this account.")
    lots, _ = lot_repository.search(fpo_id=fpo.id, page_size=5)
    return {
        "fpo": fpo.to_dict(),
        "summary": fpo_member_repository.fpo_summary(fpo.id),
        "recent_lots": lots,
    }


def _assert_fpo_owner(user, fpo):
    if user.role == ADMIN or fpo.user_id == user.id:
        return
    raise ForbiddenError("You can only manage your own FPO.")
