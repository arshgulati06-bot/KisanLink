"""Offer endpoints - where price discovery turns into a deal."""
from app.controllers import body, page_args, query
from app.middleware.auth_middleware import login_required, require_current_user
from app.middleware.role_middleware import buyer_required
from app.schemas.offer_schema import (
    COUNTER_OFFER_SCHEMA,
    CREATE_OFFER_SCHEMA,
    OFFER_FILTER_SCHEMA,
    RESPOND_SCHEMA,
)
from app.services import offer_service
from app.utils.responses import created, paginated, success


@buyer_required
def create_offer():
    return created(
        offer_service.create_offer(require_current_user(), body(CREATE_OFFER_SCHEMA)),
        message="Offer sent to the seller.",
    )


@login_required
def list_offers():
    page, page_size = page_args()
    filters = query(OFFER_FILTER_SCHEMA)
    scope = filters.pop("scope", None)
    items, total = offer_service.list_offers(
        require_current_user(), role_scope=scope, page=page, page_size=page_size, **filters
    )
    return paginated(items, page, page_size, total)


@login_required
def get_offer(offer_id):
    return success(offer_service.get_offer(offer_id, viewer=require_current_user()))


@login_required
def offers_for_lot(lot_id):
    return success(offer_service.offers_for_lot(require_current_user(), lot_id))


@login_required
def accept_offer(offer_id):
    result = offer_service.accept_offer(require_current_user(), offer_id)
    return success(result, message="Offer accepted. A transaction record has been created.")


@login_required
def reject_offer(offer_id):
    data = body(RESPOND_SCHEMA, partial=True)
    return success(
        offer_service.reject_offer(require_current_user(), offer_id, data.get("reason")),
        message="Offer rejected.",
    )


@login_required
def counter_offer(offer_id):
    return created(
        offer_service.counter_offer(require_current_user(), offer_id, body(COUNTER_OFFER_SCHEMA)),
        message="Counter-offer sent to the buyer.",
    )


@buyer_required
def withdraw_offer(offer_id):
    return success(
        offer_service.withdraw_offer(require_current_user(), offer_id),
        message="Offer withdrawn.",
    )
