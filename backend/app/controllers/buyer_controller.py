"""Buyer profile and buyer demand endpoints."""
from flask import request

from app.controllers import body, page_args, query
from app.middleware.auth_middleware import login_required, require_current_user
from app.middleware.role_middleware import buyer_required
from app.schemas.buyer_schema import (
    BUYER_FILTER_SCHEMA,
    BUYER_PROFILE_SCHEMA,
    CREATE_REQUIREMENT_SCHEMA,
    REQUIREMENT_FILTER_SCHEMA,
    UPDATE_REQUIREMENT_SCHEMA,
)
from app.services import buyer_service, matching_service
from app.utils.responses import created, paginated, success


def list_buyers():
    page, page_size = page_args()
    filters = query(BUYER_FILTER_SCHEMA)
    items, total = buyer_service.list_buyers(
        buyer_type=filters.get("buyer_type"),
        verification_status=filters.get("verification_status"),
        district=filters.get("district"),
        query=filters.get("q"),
        page=page,
        page_size=page_size,
        order_by=filters.get("order_by"),
    )
    return paginated(items, page, page_size, total)


def get_buyer(buyer_id):
    return success(buyer_service.get_buyer_detail(buyer_id))


@buyer_required
def save_profile():
    data = body(BUYER_PROFILE_SCHEMA, partial=True)
    return success(
        buyer_service.save_buyer_profile(require_current_user(), data),
        message="Buyer profile saved.",
    )


@buyer_required
def dashboard():
    return success(buyer_service.buyer_dashboard(require_current_user()))


# --- buyer demand ----------------------------------------------------------
@buyer_required
def create_requirement():
    data = body(CREATE_REQUIREMENT_SCHEMA)
    return created(
        buyer_service.create_requirement(require_current_user(), data),
        message="Requirement published. Matching farmer lots will now appear.",
    )


@login_required
def list_requirements():
    page, page_size = page_args()
    filters = query(REQUIREMENT_FILTER_SCHEMA)
    items, total = buyer_service.list_requirements(
        viewer=require_current_user(),
        mine=request.args.get("mine") == "true",
        page=page,
        page_size=page_size,
        **filters,
    )
    return paginated(items, page, page_size, total)


def get_requirement(requirement_id):
    return success(buyer_service.get_requirement_detail(requirement_id))


@buyer_required
def update_requirement(requirement_id):
    data = body(UPDATE_REQUIREMENT_SCHEMA, partial=True)
    return success(
        buyer_service.update_requirement(require_current_user(), requirement_id, data),
        message="Requirement updated.",
    )


@buyer_required
def close_requirement(requirement_id):
    return success(
        buyer_service.close_requirement(require_current_user(), requirement_id),
        message="Requirement closed.",
    )


@login_required
def requirement_matches(requirement_id):
    limit = int(request.args.get("limit", 10))
    return success(matching_service.match_requirement(requirement_id, limit=limit))
