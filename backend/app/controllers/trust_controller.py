"""Verification, ratings and grievance endpoints."""
from app.controllers import body, page_args, query
from app.middleware.auth_middleware import login_required, require_current_user
from app.middleware.role_middleware import admin_required
from app.schemas.trust_schema import (
    CREATE_GRIEVANCE_SCHEMA,
    GRIEVANCE_FILTER_SCHEMA,
    RATE_SCHEMA,
    UPDATE_GRIEVANCE_SCHEMA,
    VERIFY_BUYER_SCHEMA,
)
from app.services import trust_service
from app.utils.responses import created, paginated, success


# --- trust -----------------------------------------------------------------
def buyer_trust(buyer_id):
    """Public trust breakdown, so the score can be interrogated, not just seen."""
    return success(trust_service.trust_profile(buyer_id))


@admin_required
def verify_buyer(buyer_id):
    data = body(VERIFY_BUYER_SCHEMA)
    return success(
        trust_service.set_verification(
            require_current_user(), buyer_id, data["verification_status"], data.get("notes")
        ),
        message="Verification status updated.",
    )


@admin_required
def pending_verifications():
    page, page_size = page_args()
    buyers, total = trust_service.pending_verifications(page=page, page_size=page_size)
    return paginated([buyer.to_dict() for buyer in buyers], page, page_size, total)


# --- ratings ---------------------------------------------------------------
@login_required
def rate():
    data = body(RATE_SCHEMA)
    return created(
        trust_service.rate_counterparty(require_current_user(), data["transaction_id"], data),
        message="Thank you. Your rating has been recorded.",
    )


def user_ratings(user_id):
    return success(trust_service.ratings_for_user(user_id))


# --- grievances ------------------------------------------------------------
@login_required
def create_grievance():
    return created(
        trust_service.raise_grievance(require_current_user(), body(CREATE_GRIEVANCE_SCHEMA)),
        message="Grievance registered. You will be notified as it is reviewed.",
    )


@login_required
def list_grievances():
    page, page_size = page_args()
    filters = query(GRIEVANCE_FILTER_SCHEMA)
    scope = filters.pop("scope", None)
    items, total = trust_service.list_grievances(
        require_current_user(), scope=scope, page=page, page_size=page_size, **filters
    )
    return paginated([item if isinstance(item, dict) else item.to_dict() for item in items],
                     page, page_size, total)


@login_required
def get_grievance(grievance_id):
    return success(trust_service.get_grievance(require_current_user(), grievance_id))


@login_required
def update_grievance(grievance_id):
    data = body(UPDATE_GRIEVANCE_SCHEMA)
    return success(
        trust_service.update_grievance_status(
            require_current_user(), grievance_id, data["status"], data.get("resolution")
        ),
        message=f"Grievance moved to {data['status']}.",
    )


@admin_required
def grievance_dashboard():
    return success(trust_service.grievance_dashboard())
