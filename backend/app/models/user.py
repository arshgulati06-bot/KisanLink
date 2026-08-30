"""Account record. One row per person, whatever their role."""
from dataclasses import dataclass, field

from app.models import BaseModel

FARMER = "FARMER"
FPO = "FPO"
BUYER = "BUYER"
ADMIN = "ADMIN"

ROLES = (FARMER, FPO, BUYER, ADMIN)
#: Roles that can own a lot and sell it.
SELLER_ROLES = (FARMER, FPO)


@dataclass
class User(BaseModel):
    BOOL_FIELDS = ("is_active",)

    id: int = None
    name: str = None
    phone: str = None
    email: str = None
    password_hash: str = field(default=None, repr=False)
    role: str = None
    language: str = "en"
    is_active: int = 1
    created_at: str = None
    updated_at: str = None

    def to_dict(self, extra=None):
        """Never let the password hash reach a response body."""
        data = super().to_dict(extra)
        data.pop("password_hash", None)
        return data

    @property
    def is_seller(self):
        return self.role in SELLER_ROLES
