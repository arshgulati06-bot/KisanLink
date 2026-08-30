"""FPO profile, membership and aggregation endpoints."""
from flask import request

from app.controllers import body, page_args
from app.middleware.auth_middleware import login_required, require_current_user
from app.middleware.role_middleware import fpo_required
from app.schemas.fpo_schema import (
    ADD_MEMBER_SCHEMA,
    AGGREGATE_SCHEMA,
    CANDIDATES_SCHEMA,
    FPO_PROFILE_SCHEMA,
    UPDATE_MEMBER_SCHEMA,
)
from app.schemas import validate
from app.services import fpo_service
from app.utils.responses import created, paginated, success


def list_fpos():
    page, page_size = page_args()
    items, total = fpo_service.list_fpos(
        district=request.args.get("district"),
        state=request.args.get("state"),
        page=page,
        page_size=page_size,
        order_by=request.args.get("order_by"),
    )
    return paginated(items, page, page_size, total)


def get_fpo(fpo_id):
    return success(fpo_service.get_fpo_detail(fpo_id))


@fpo_required
def save_profile():
    data = body(FPO_PROFILE_SCHEMA, partial=True)
    return success(fpo_service.save_profile(require_current_user(), data), message="FPO profile saved.")


@fpo_required
def dashboard():
    return success(fpo_service.fpo_dashboard(require_current_user()))


def list_members(fpo_id):
    return success(fpo_service.list_members(fpo_id, status=request.args.get("status")))


@fpo_required
def add_member(fpo_id):
    return created(
        fpo_service.add_member(require_current_user(), fpo_id, body(ADD_MEMBER_SCHEMA)),
        message="Member added.",
    )


@fpo_required
def update_member(fpo_id, member_id):
    data = body(UPDATE_MEMBER_SCHEMA, partial=True)
    return success(
        fpo_service.update_member(require_current_user(), fpo_id, member_id, data),
        message="Membership updated.",
    )


@fpo_required
def remove_member(fpo_id, member_id):
    fpo_service.remove_member(require_current_user(), fpo_id, member_id)
    return success(message="Member removed.")


@fpo_required
def aggregation_candidates(fpo_id):
    filters = validate(request.args.to_dict(), CANDIDATES_SCHEMA)
    return success(
        fpo_service.aggregation_candidates(require_current_user(), fpo_id, filters["crop_id"])
    )


@fpo_required
def aggregate(fpo_id):
    return created(
        fpo_service.aggregate_lots(require_current_user(), fpo_id, body(AGGREGATE_SCHEMA)),
        message="Member lots pooled into one aggregated lot.",
    )


@login_required
def payouts(fpo_id, lot_id):
    return success(fpo_service.contribution_payouts(fpo_id, lot_id))
