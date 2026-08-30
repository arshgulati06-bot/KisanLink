"""
How much each member farmer put into an aggregated FPO lot.

Keeping contributions separate is what makes a fair payout split possible once
the transaction is paid.
"""
from dataclasses import dataclass

from app.models import BaseModel


@dataclass
class LotContribution(BaseModel):
    FLOAT_FIELDS = ("quantity", "payout_amount")

    id: int = None
    lot_id: int = None
    farmer_id: int = None
    quantity: float = None
    grade: str = "B"
    payout_amount: float = None
    created_at: str = None
