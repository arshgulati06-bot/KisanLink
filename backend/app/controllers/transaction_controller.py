"""Transaction and payment endpoints."""
from app.controllers import body, page_args, query
from app.middleware.auth_middleware import login_required, require_current_user
from app.schemas.transaction_schema import (
    RECORD_PAYMENT_SCHEMA,
    TRANSACTION_FILTER_SCHEMA,
    UPDATE_STATUS_SCHEMA,
)
from app.services import transaction_service
from app.utils.responses import created, paginated, success


@login_required
def list_transactions():
    page, page_size = page_args()
    filters = query(TRANSACTION_FILTER_SCHEMA)
    scope = filters.pop("scope", None)
    items, total = transaction_service.list_transactions(
        require_current_user(), role_scope=scope, page=page, page_size=page_size, **filters
    )
    return paginated(items, page, page_size, total)


@login_required
def get_transaction(transaction_id):
    return success(transaction_service.get_transaction(transaction_id, viewer=require_current_user()))


@login_required
def update_status(transaction_id):
    data = body(UPDATE_STATUS_SCHEMA)
    return success(
        transaction_service.update_status(
            require_current_user(), transaction_id, data["status"], data.get("remarks")
        ),
        message=f"Transaction moved to {data['status']}.",
    )


@login_required
def history(transaction_id):
    return success(
        transaction_service.transaction_history(transaction_id, viewer=require_current_user())
    )


@login_required
def record_payment(transaction_id):
    return created(
        transaction_service.record_payment(
            require_current_user(), transaction_id, body(RECORD_PAYMENT_SCHEMA)
        ),
        message="Payment recorded.",
    )


@login_required
def realization(transaction_id):
    return success(
        transaction_service.net_realization_breakdown(
            transaction_id, viewer=require_current_user()
        )
    )


@login_required
def summary():
    return success(transaction_service.summary_for(require_current_user()))
