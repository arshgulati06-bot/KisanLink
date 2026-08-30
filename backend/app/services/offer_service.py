"""
Digital offers.

Offers are the point where price discovery becomes a transaction. They move in
both directions - a buyer offers, the farmer can counter - and acceptance is
the single action that creates a transaction record.
"""
import datetime as dt

from app.models.lot import LISTED, OFFER_RECEIVED, OPEN_STATUSES, SOLD
from app.models.offer import ACCEPTED, COUNTERED, LIVE_STATUSES, PENDING, REJECTED, WITHDRAWN
from app.models.user import ADMIN
from app.repositories.buyer_repository import buyer_requirement_repository
from app.repositories.lot_repository import lot_repository
from app.repositories.offer_repository import offer_repository
from app.repositories.user_repository import buyer_profile_repository
from app.services import transaction_service
from app.utils.responses import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.utils.units import convert_quantity


def create_offer(user, data):
    """
    A buyer makes an offer on a lot.

    One live offer per buyer per lot: a buyer who wants to change their price
    withdraws or counters rather than stacking offers the farmer has to compare
    against each other.
    """
    buyer = _require_buyer(user)
    lot = lot_repository.find_by_id(data["lot_id"])
    if not lot:
        raise NotFoundError("Lot not found.")
    if lot.status not in OPEN_STATUSES:
        raise ConflictError(
            f"This lot is {lot.status.lower()} and is not accepting offers."
        )
    if lot.seller_user_id == user.id:
        raise ValidationError("You cannot make an offer on your own lot.")
    if offer_repository.has_live_offer(lot.id, buyer.id):
        raise ConflictError(
            "You already have a pending offer on this lot. "
            "Withdraw it before making a new one."
        )

    unit = (data.get("unit") or lot.unit).upper()
    quantity = float(data.get("quantity") or 0) or float(lot.quantity)
    quantity_in_lot_unit = convert_quantity(quantity, unit, lot.unit)
    if quantity_in_lot_unit is None or quantity_in_lot_unit <= 0:
        raise ValidationError("'quantity' must be greater than zero.")
    if quantity_in_lot_unit > float(lot.quantity) + 1e-6:
        raise ValidationError(
            f"Offer quantity exceeds the lot size of {float(lot.quantity):,.2f} {lot.unit}."
        )

    requirement_id = data.get("requirement_id")
    if requirement_id:
        requirement = buyer_requirement_repository.find_by_id(requirement_id)
        if not requirement or requirement.buyer_id != buyer.id:
            raise ValidationError("'requirement_id' does not belong to this buyer.")

    payload = dict(data)
    payload.update(
        {
            "buyer_id": buyer.id,
            "seller_user_id": lot.seller_user_id,
            "quantity": quantity,
            "unit": unit,
            "status": PENDING,
            "initiated_by": "BUYER",
        }
    )
    offer_id = offer_repository.insert(payload)
    if lot.status == LISTED:
        lot_repository.set_status(lot.id, OFFER_RECEIVED)
    return offer_repository.detail(offer_id)


def counter_offer(user, offer_id, data):
    """
    The farmer counters a buyer's price.

    The original offer becomes COUNTERED and a new offer is created that points
    back at it, so the whole negotiation stays readable afterwards.
    """
    offer = _get_offer(offer_id)
    lot = lot_repository.find_by_id(offer.lot_id)
    if offer.seller_user_id != user.id and user.role != ADMIN:
        raise ForbiddenError("Only the seller of this lot can counter an offer.")
    if offer.status not in LIVE_STATUSES:
        raise ConflictError(f"A {offer.status.lower()} offer cannot be countered.")

    quantity = float(data.get("quantity") or offer.quantity)
    unit = (data.get("unit") or offer.unit).upper()
    if convert_quantity(quantity, unit, lot.unit) > float(lot.quantity) + 1e-6:
        raise ValidationError("Counter quantity exceeds the lot size.")

    offer_repository.set_status(offer_id, COUNTERED)
    new_id = offer_repository.insert(
        {
            "lot_id": offer.lot_id,
            "requirement_id": offer.requirement_id,
            "buyer_id": offer.buyer_id,
            "seller_user_id": offer.seller_user_id,
            "price_per_unit": data["price_per_unit"],
            "quantity": quantity,
            "unit": unit,
            "delivery_mode": data.get("delivery_mode") or offer.delivery_mode,
            "transport_borne_by": data.get("transport_borne_by") or offer.transport_borne_by,
            "payment_terms_days": data.get("payment_terms_days") or offer.payment_terms_days,
            "valid_until": data.get("valid_until"),
            "status": PENDING,
            "initiated_by": "FARMER",
            "parent_offer_id": offer.id,
            "message": data.get("message"),
        }
    )
    return offer_repository.detail(new_id)


def accept_offer(user, offer_id):
    """
    Accept an offer and open the transaction.

    Accepting is the point of no return for the lot: it is marked SOLD, every
    other live offer on it is rejected, and the buyer's requirement is debited
    by the quantity committed.
    """
    offer = _get_offer(offer_id)
    lot = lot_repository.find_by_id(offer.lot_id)
    if not lot:
        raise NotFoundError("The lot for this offer no longer exists.")

    _assert_can_respond(user, offer)
    if offer.status not in LIVE_STATUSES:
        raise ConflictError(f"A {offer.status.lower()} offer cannot be accepted.")
    if lot.status == SOLD:
        raise ConflictError("This lot has already been sold.")

    offer_repository.set_status(offer_id, ACCEPTED)
    offer_repository.reject_other_offers(lot.id, offer_id)
    lot_repository.set_status(lot.id, SOLD)
    if offer.requirement_id:
        buyer_requirement_repository.add_fulfilled_quantity(offer.requirement_id, offer.quantity)

    transaction = transaction_service.create_from_offer(offer_repository.find_by_id(offer_id), user)
    return {"offer": offer_repository.detail(offer_id), "transaction": transaction}


def reject_offer(user, offer_id, reason=None):
    offer = _get_offer(offer_id)
    _assert_can_respond(user, offer)
    if offer.status not in LIVE_STATUSES:
        raise ConflictError(f"A {offer.status.lower()} offer cannot be rejected.")
    offer_repository.set_status(offer_id, REJECTED, remarks=reason)
    _restore_lot_status(offer.lot_id)
    return offer_repository.detail(offer_id)


def withdraw_offer(user, offer_id):
    """The buyer pulls their own offer back."""
    offer = _get_offer(offer_id)
    buyer = buyer_profile_repository.find_by_user_id(user.id)
    if user.role != ADMIN and (not buyer or buyer.id != offer.buyer_id):
        raise ForbiddenError("Only the buyer who made this offer can withdraw it.")
    if offer.status not in LIVE_STATUSES:
        raise ConflictError(f"A {offer.status.lower()} offer cannot be withdrawn.")
    offer_repository.set_status(offer_id, WITHDRAWN)
    _restore_lot_status(offer.lot_id)
    return offer_repository.detail(offer_id)


def _restore_lot_status(lot_id):
    """Put a lot back to LISTED once no live offers remain."""
    lot = lot_repository.find_by_id(lot_id)
    if not lot or lot.status != OFFER_RECEIVED:
        return
    if not offer_repository.count_for_lot(lot_id, statuses=list(LIVE_STATUSES)):
        lot_repository.set_status(lot_id, LISTED)


def get_offer(offer_id, viewer=None):
    detail = offer_repository.detail(offer_id)
    if not detail:
        raise NotFoundError("Offer not found.")
    if viewer is not None:
        buyer = buyer_profile_repository.find_by_user_id(viewer.id)
        detail["can_respond"] = detail["seller_user_id"] == viewer.id
        detail["is_own_offer"] = bool(buyer and buyer.id == detail["buyer_id"])
    return detail


def list_offers(viewer, role_scope=None, **filters):
    """
    List offers, scoped to whoever is asking.

    A farmer sees offers made to them; a buyer sees offers they made. Without
    this scoping the endpoint would leak one party's negotiation to the other.
    """
    if viewer.role == ADMIN and role_scope == "all":
        return offer_repository.search(**filters)
    buyer = buyer_profile_repository.find_by_user_id(viewer.id)
    if buyer and role_scope != "seller":
        filters["buyer_id"] = buyer.id
    else:
        filters["seller_user_id"] = viewer.id
    return offer_repository.search(**filters)


def offers_for_lot(user, lot_id):
    lot = lot_repository.find_by_id(lot_id)
    if not lot:
        raise NotFoundError("Lot not found.")
    if lot.seller_user_id != user.id and user.role != ADMIN:
        raise ForbiddenError("Only the seller can see all offers on this lot.")
    return offer_repository.live_offers_for_lot(lot_id)


def expire_stale_offers():
    return offer_repository.expire_stale(dt.date.today().isoformat())


def _get_offer(offer_id):
    offer = offer_repository.find_by_id(offer_id)
    if not offer:
        raise NotFoundError("Offer not found.")
    return offer


def _require_buyer(user):
    buyer = buyer_profile_repository.find_by_user_id(user.id)
    if not buyer:
        raise NotFoundError(
            "No buyer profile found for this account. Create your buyer profile first."
        )
    return buyer


def _assert_can_respond(user, offer):
    """
    Only the party the offer was sent TO may accept or reject it.

    A buyer-initiated offer is answered by the farmer; a farmer's counter is
    answered by the buyer.
    """
    if user.role == ADMIN:
        return
    if offer.initiated_by == "BUYER":
        if offer.seller_user_id == user.id:
            return
        raise ForbiddenError("Only the seller of this lot can respond to this offer.")
    buyer = buyer_profile_repository.find_by_user_id(user.id)
    if buyer and buyer.id == offer.buyer_id:
        return
    raise ForbiddenError("Only the buyer can respond to this counter-offer.")
