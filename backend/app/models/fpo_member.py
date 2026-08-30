"""Membership link between an FPO and a farmer."""
from dataclasses import dataclass

from app.models import BaseModel

MEMBER = "MEMBER"
BOARD_MEMBER = "BOARD_MEMBER"
CHAIRPERSON = "CHAIRPERSON"
MEMBER_ROLES = (MEMBER, BOARD_MEMBER, CHAIRPERSON)

PENDING = "PENDING"
ACTIVE = "ACTIVE"
INACTIVE = "INACTIVE"
REMOVED = "REMOVED"
MEMBER_STATUSES = (PENDING, ACTIVE, INACTIVE, REMOVED)


@dataclass
class FpoMember(BaseModel):
    id: int = None
    fpo_id: int = None
    farmer_id: int = None
    member_role: str = MEMBER
    status: str = ACTIVE
    joined_at: str = None
