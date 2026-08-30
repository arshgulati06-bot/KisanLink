"""
Buyer record.

The problem statement names processors and institutional buyers explicitly, so
buyer_type is a first-class field rather than a free-text label.

verification_status is a PLATFORM status. PLATFORM_REVIEWED means KisanLink
staff looked at the submitted documents - it is not a claim of government KYC
or GST verification.
"""
from dataclasses import dataclass

from app.models import BaseModel

PROCESSOR = "PROCESSOR"
INSTITUTIONAL = "INSTITUTIONAL"
AGGREGATOR = "AGGREGATOR"
TRADER = "TRADER"
EXPORTER = "EXPORTER"
OTHER = "OTHER"

BUYER_TYPES = (PROCESSOR, INSTITUTIONAL, AGGREGATOR, TRADER, EXPORTER, OTHER)

UNVERIFIED = "UNVERIFIED"
DOCUMENTS_SUBMITTED = "DOCUMENTS_SUBMITTED"
PLATFORM_REVIEWED = "PLATFORM_REVIEWED"
REJECTED = "REJECTED"

VERIFICATION_STATUSES = (UNVERIFIED, DOCUMENTS_SUBMITTED, PLATFORM_REVIEWED, REJECTED)

#: Shown to farmers next to every buyer, so the wording is fixed here.
VERIFICATION_LABELS = {
    UNVERIFIED: "Not verified by the platform",
    DOCUMENTS_SUBMITTED: "Documents submitted, review pending",
    PLATFORM_REVIEWED: "Platform-Reviewed",
    REJECTED: "Verification rejected",
}


@dataclass
class BuyerProfile(BaseModel):
    BOOL_FIELDS = ("is_seed_data",)
    FLOAT_FIELDS = (
        "latitude",
        "longitude",
        "trust_score",
        "on_time_payment_rate",
    )

    id: int = None
    user_id: int = None
    business_name: str = None
    buyer_type: str = TRADER
    gst_number: str = None
    license_number: str = None
    address: str = None
    district: str = None
    state: str = "Maharashtra"
    latitude: float = None
    longitude: float = None
    verification_status: str = UNVERIFIED
    verification_notes: str = None
    verified_at: str = None
    trust_score: float = 40.0
    total_transactions: int = 0
    completed_transactions: int = 0
    on_time_payment_rate: float = None
    is_seed_data: int = 0
    created_at: str = None
    updated_at: str = None

    def to_dict(self, extra=None):
        data = super().to_dict(extra)
        data["verification_label"] = VERIFICATION_LABELS.get(
            self.verification_status, self.verification_status
        )
        return data
