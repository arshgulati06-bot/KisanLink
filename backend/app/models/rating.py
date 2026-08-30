"""Counterparty feedback left after a completed transaction."""
from dataclasses import dataclass

from app.models import BaseModel

MIN_SCORE = 1.0
MAX_SCORE = 5.0


@dataclass
class Rating(BaseModel):
    FLOAT_FIELDS = ("score", "payment_score", "quality_score", "punctuality_score")

    id: int = None
    transaction_id: int = None
    rater_user_id: int = None
    rated_user_id: int = None
    score: float = None
    payment_score: float = None
    quality_score: float = None
    punctuality_score: float = None
    comment: str = None
    created_at: str = None
