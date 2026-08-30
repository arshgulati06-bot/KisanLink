"""Lot endpoints - the farmer's supply side."""
from flask import request

from app.controllers import body, page_args, query
from app.middleware.auth_middleware import login_required, optional_login, require_current_user
from app.middleware.role_middleware import seller_required
from app.schemas.lot_schema import (
    CREATE_LOT_SCHEMA,
    LOT_FILTER_SCHEMA,
    SET_STATUS_SCHEMA,
    UPDATE_LOT_SCHEMA,
    WITHDRAW_SCHEMA,
)
from app.services import lot_service, matching_service, recommendation_service
from app.utils.responses import created, paginated, success


@seller_required
def create_lot():
    user = require_current_user()
    return created(lot_service.create_lot(user, body(CREATE_LOT_SCHEMA)), message="Lot created.")


@optional_login
def list_lots():
    from app.middleware.auth_middleware import current_user

    page, page_size = page_args()
    filters = query(LOT_FILTER_SCHEMA)
    items, total = lot_service.list_lots(
        viewer=current_user(),
        mine=request.args.get("mine") == "true",
        page=page,
        page_size=page_size,
        **filters,
    )
    return paginated(items, page, page_size, total)


@optional_login
def get_lot(lot_id):
    from app.middleware.auth_middleware import current_user

    return success(
        lot_service.get_lot_detail(
            lot_id,
            include_offers=request.args.get("include_offers") == "true",
            viewer=current_user(),
        )
    )


@login_required
def update_lot(lot_id):
    data = body(UPDATE_LOT_SCHEMA, partial=True)
    return success(lot_service.update_lot(require_current_user(), lot_id, data), message="Lot updated.")


@login_required
def publish_lot(lot_id):
    return success(
        lot_service.publish_lot(require_current_user(), lot_id),
        message="Lot published. Buyers can now see it.",
    )


@login_required
def withdraw_lot(lot_id):
    data = body(WITHDRAW_SCHEMA, partial=True)
    return success(
        lot_service.withdraw_lot(require_current_user(), lot_id, data.get("reason")),
        message="Lot withdrawn.",
    )


@login_required
def set_status(lot_id):
    data = body(SET_STATUS_SCHEMA)
    return success(
        lot_service.set_status(require_current_user(), lot_id, data["status"]),
        message="Lot status updated.",
    )


@login_required
def delete_lot(lot_id):
    lot_service.delete_lot(require_current_user(), lot_id)
    return success(message="Draft lot deleted.")


@login_required
def lot_matches(lot_id):
    limit = int(request.args.get("limit", 10))
    return success(matching_service.match_lot(lot_id, limit=limit))


@login_required
def lot_recommendation(lot_id):
    return success(
        recommendation_service.recommend_for_lot(
            lot_id,
            horizon_days=request.args.get("horizon_days"),
            include_markets=request.args.get("include_markets") != "false",
            store=request.args.get("store") != "false",
        )
    )


@seller_required
def dashboard():
    return success(lot_service.seller_dashboard(require_current_user()))
