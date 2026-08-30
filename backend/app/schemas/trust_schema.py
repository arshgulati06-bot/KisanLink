"""Request shapes for verification, ratings and grievances."""
from app.models.buyer_profile import VERIFICATION_STATUSES
from app.models.grievance import CATEGORIES, STATUSES
from app.models.rating import MAX_SCORE, MIN_SCORE
from app.schemas import Field

VERIFY_BUYER_SCHEMA = {
    "verification_status": Field(str, required=True, choices=VERIFICATION_STATUSES),
    "notes": Field(str, max_len=255),
}

RATE_SCHEMA = {
    "transaction_id": Field(int, required=True, min_value=1),
    "score": Field(float, required=True, min_value=MIN_SCORE, max_value=MAX_SCORE),
    "payment_score": Field(float, min_value=MIN_SCORE, max_value=MAX_SCORE),
    "quality_score": Field(float, min_value=MIN_SCORE, max_value=MAX_SCORE),
    "punctuality_score": Field(float, min_value=MIN_SCORE, max_value=MAX_SCORE),
    "comment": Field(str, max_len=500),
}

CREATE_GRIEVANCE_SCHEMA = {
    "transaction_id": Field(int, min_value=1),
    "against_user_id": Field(int, min_value=1),
    "category": Field(str, choices=CATEGORIES, default="OTHER"),
    "subject": Field(str, required=True, min_len=5, max_len=180),
    "description": Field(str, required=True, min_len=10, max_len=2000),
}

UPDATE_GRIEVANCE_SCHEMA = {
    "status": Field(str, required=True, choices=STATUSES),
    "resolution": Field(str, max_len=2000),
}

GRIEVANCE_FILTER_SCHEMA = {
    "status": Field(str, choices=STATUSES),
    "category": Field(str, choices=CATEGORIES),
    "transaction_id": Field(int, min_value=1),
    "scope": Field(str, choices=("mine", "against_me", "all")),
    "order_by": Field(str, max_len=40),
}
