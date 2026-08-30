"""
Trust, verification, ratings and grievances.

"Payment reliability" and "buyer credentials" are named directly in the problem
statement, so they get a real, computed treatment here rather than a badge.

The trust score is a transparent 0-100 composite of things the platform can
actually observe: whether documents were reviewed, what counterparties rated
them, how many deals completed, whether payments landed on time, and whether
grievances are open. Its components are returned alongside the number, because
a score a farmer cannot interrogate is not trust - it is just a badge with
extra steps.
"""
import datetime as dt

from app.models.buyer_profile import PLATFORM_REVIEWED, VERIFICATION_LABELS, VERIFICATION_STATUSES
from app.models.grievance import CATEGORIES, CLOSED_STATUSES, STATUS_FLOW, STATUSES
from app.models.rating import MAX_SCORE, MIN_SCORE
from app.models.transaction import COMPLETED, PAID
from app.models.user import ADMIN
from app.repositories.transaction_repository import (
    payment_repository,
    transaction_repository,
)
from app.repositories.trust_repository import grievance_repository, rating_repository
from app.repositories.user_repository import buyer_profile_repository, user_repository
from app.utils.responses import ConflictError, ForbiddenError, NotFoundError, ValidationError

#: Maximum points each signal can contribute to the 0-100 trust score.
TRUST_WEIGHTS = {
    "verification": 30,
    "ratings": 25,
    "completed_transactions": 15,
    "payment_punctuality": 25,
    "grievance_penalty": -15,
}

#: Completed deals at which the volume component maxes out.
VOLUME_SATURATION = 10

VERIFICATION_POINTS = {
    "PLATFORM_REVIEWED": 1.0,
    "DOCUMENTS_SUBMITTED": 0.5,
    "UNVERIFIED": 0.2,
    "REJECTED": 0.0,
}


# ---------------------------------------------------------------------------
# Trust scoring
# ---------------------------------------------------------------------------
def compute_trust(buyer):
    """
    Work out a buyer's trust score and show the arithmetic.

    A brand-new buyer is not treated as untrustworthy, only as unproven: the
    components they have no history for simply score nothing, and the response
    says so.
    """
    aggregate = rating_repository.aggregate_for_user(buyer.user_id)
    punctuality = payment_repository.payment_punctuality(buyer.id)
    open_grievances = grievance_repository.open_count_against(buyer.user_id)
    total, completed = (
        int(buyer.total_transactions or 0),
        int(buyer.completed_transactions or 0),
    )

    components = {}

    verification_fraction = VERIFICATION_POINTS.get(
        str(buyer.verification_status or "UNVERIFIED").upper(), 0.2
    )
    components["verification"] = {
        "points": round(TRUST_WEIGHTS["verification"] * verification_fraction, 2),
        "max_points": TRUST_WEIGHTS["verification"],
        "detail": VERIFICATION_LABELS.get(buyer.verification_status, buyer.verification_status),
    }

    rating_count = int(aggregate.get("rating_count") or 0)
    average_score = float(aggregate.get("average_score") or 0)
    if rating_count:
        # Normalise a 1-5 rating onto 0-1, then damp it while the sample is
        # small so three glowing reviews cannot manufacture a top score.
        normalised = (average_score - MIN_SCORE) / (MAX_SCORE - MIN_SCORE)
        confidence = min(1.0, rating_count / 5.0)
        fraction = normalised * confidence
        detail = f"{average_score:.1f}/5 from {rating_count} rating(s)"
    else:
        fraction, detail = 0.0, "No ratings yet"
    components["ratings"] = {
        "points": round(TRUST_WEIGHTS["ratings"] * fraction, 2),
        "max_points": TRUST_WEIGHTS["ratings"],
        "detail": detail,
    }

    volume_fraction = min(1.0, completed / VOLUME_SATURATION) if completed else 0.0
    components["completed_transactions"] = {
        "points": round(TRUST_WEIGHTS["completed_transactions"] * volume_fraction, 2),
        "max_points": TRUST_WEIGHTS["completed_transactions"],
        "detail": f"{completed} completed of {total} transaction(s)",
    }

    if punctuality is None:
        punctuality_fraction, punctuality_detail = 0.0, "No settled payments yet"
    else:
        punctuality_fraction = punctuality / 100.0
        punctuality_detail = f"{punctuality:.0f}% of payments made on or before the due date"
    components["payment_punctuality"] = {
        "points": round(TRUST_WEIGHTS["payment_punctuality"] * punctuality_fraction, 2),
        "max_points": TRUST_WEIGHTS["payment_punctuality"],
        "detail": punctuality_detail,
    }

    penalty = 0.0
    if open_grievances:
        penalty = min(abs(TRUST_WEIGHTS["grievance_penalty"]), 5.0 * open_grievances)
    components["grievance_penalty"] = {
        "points": round(-penalty, 2),
        "max_points": TRUST_WEIGHTS["grievance_penalty"],
        "detail": (
            f"{open_grievances} open grievance(s)" if open_grievances else "No open grievances"
        ),
    }

    score = max(0.0, min(100.0, sum(part["points"] for part in components.values())))
    evidence_count = rating_count + completed + (0 if punctuality is None else 1)
    return {
        "trust_score": round(score, 2),
        "components": components,
        "evidence_points": evidence_count,
        "is_provisional": evidence_count < 3,
        "note": (
            "This score is based on very little platform history so far and should be read "
            "as provisional."
            if evidence_count < 3
            else "Computed from platform activity only."
        ),
        "disclaimer": (
            "Verification reflects a KisanLink platform review. It is not a government "
            "KYC or GST verification."
        ),
        "on_time_payment_rate": punctuality,
        "open_grievances": open_grievances,
    }


def recalculate_buyer_trust(buyer_id):
    """Recompute and store a buyer's trust score after anything that could move it."""
    buyer = buyer_profile_repository.find_by_id(buyer_id)
    if not buyer:
        return None
    result = compute_trust(buyer)
    buyer_profile_repository.update(
        buyer_id,
        {
            "trust_score": result["trust_score"],
            "on_time_payment_rate": result["on_time_payment_rate"],
        },
    )
    return result


def trust_profile(buyer_id):
    buyer = buyer_profile_repository.find_by_id(buyer_id)
    if not buyer:
        raise NotFoundError("Buyer not found.")
    result = compute_trust(buyer)
    result["buyer"] = buyer.to_dict()
    result["recent_ratings"] = rating_repository.for_user(buyer.user_id, limit=10)
    return result


# ---------------------------------------------------------------------------
# Verification (admin)
# ---------------------------------------------------------------------------
def set_verification(admin_user, buyer_id, status, notes=None):
    """
    Set a buyer's platform verification status.

    Restricted to administrators on purpose: a self-serve "verified" flag would
    make the whole trust signal worthless.
    """
    if admin_user.role != ADMIN:
        raise ForbiddenError("Only an administrator can change verification status.")
    buyer = buyer_profile_repository.find_by_id(buyer_id)
    if not buyer:
        raise NotFoundError("Buyer not found.")
    status = status.upper()
    if status not in VERIFICATION_STATUSES:
        raise ValidationError(
            f"'verification_status' must be one of: {', '.join(VERIFICATION_STATUSES)}."
        )
    if status == PLATFORM_REVIEWED and not notes:
        raise ValidationError(
            "Record what was reviewed in 'notes' before marking a buyer as platform-reviewed."
        )
    buyer_profile_repository.set_verification(buyer_id, status, notes)
    recalculate_buyer_trust(buyer_id)
    return buyer_profile_repository.find_by_id(buyer_id).to_dict()


def pending_verifications(page=1, page_size=20):
    return buyer_profile_repository.search(
        verification_status="DOCUMENTS_SUBMITTED", page=page, page_size=page_size
    )


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------
def rate_counterparty(user, transaction_id, data):
    """
    Rate the other party after a deal.

    Only allowed once the transaction has actually concluded, and only once per
    person per transaction, so ratings stay tied to real trade.
    """
    transaction = transaction_repository.find_by_id(transaction_id)
    if not transaction:
        raise NotFoundError("Transaction not found.")
    if transaction.status not in (PAID, COMPLETED):
        raise ConflictError(
            "You can rate the other party once the transaction is paid or completed."
        )

    buyer = buyer_profile_repository.find_by_id(transaction.buyer_id)
    if user.id == transaction.seller_user_id:
        rated_user_id = buyer.user_id
    elif buyer and buyer.user_id == user.id:
        rated_user_id = transaction.seller_user_id
    else:
        raise ForbiddenError("You are not a party to this transaction.")

    if rating_repository.already_rated(transaction_id, user.id):
        raise ConflictError("You have already rated this transaction.")

    payload = dict(data)
    payload.update(
        {
            "transaction_id": transaction_id,
            "rater_user_id": user.id,
            "rated_user_id": rated_user_id,
        }
    )
    rating_id = rating_repository.insert(payload)
    if rated_user_id == buyer.user_id:
        recalculate_buyer_trust(buyer.id)
    return rating_repository.find_by_id(rating_id).to_dict()


def ratings_for_user(user_id, limit=50):
    user = user_repository.find_by_id(user_id)
    if not user:
        raise NotFoundError("User not found.")
    return {
        "user": user.to_dict(),
        "summary": rating_repository.aggregate_for_user(user_id),
        "ratings": rating_repository.for_user(user_id, limit=limit),
    }


# ---------------------------------------------------------------------------
# Grievances
# ---------------------------------------------------------------------------
def raise_grievance(user, data):
    """Open a dispute, optionally against a specific transaction."""
    category = (data.get("category") or "OTHER").upper()
    if category not in CATEGORIES:
        raise ValidationError(f"'category' must be one of: {', '.join(CATEGORIES)}.")

    against_user_id = data.get("against_user_id")
    transaction_id = data.get("transaction_id")
    if transaction_id:
        transaction = transaction_repository.find_by_id(transaction_id)
        if not transaction:
            raise NotFoundError("Transaction not found.")
        buyer = buyer_profile_repository.find_by_id(transaction.buyer_id)
        is_seller = transaction.seller_user_id == user.id
        is_buyer = bool(buyer and buyer.user_id == user.id)
        if not (is_seller or is_buyer or user.role == ADMIN):
            raise ForbiddenError("You are not a party to this transaction.")
        # Default the respondent to the other side of the deal.
        if not against_user_id:
            against_user_id = buyer.user_id if is_seller else transaction.seller_user_id

    payload = dict(data)
    payload.update(
        {
            "ticket_no": grievance_repository.next_ticket(),
            "raised_by_user_id": user.id,
            "against_user_id": against_user_id,
            "category": category,
            "status": "OPEN",
        }
    )
    grievance_id = grievance_repository.insert(payload)

    if against_user_id:
        buyer = buyer_profile_repository.find_by_user_id(against_user_id)
        if buyer:
            recalculate_buyer_trust(buyer.id)
    return grievance_repository.detail(grievance_id)


def get_grievance(user, grievance_id):
    detail = grievance_repository.detail(grievance_id)
    if not detail:
        raise NotFoundError("Grievance not found.")
    if user.role != ADMIN and user.id not in (
        detail["raised_by_user_id"],
        detail.get("against_user_id"),
    ):
        raise ForbiddenError("You do not have access to this grievance.")
    return detail


def list_grievances(user, scope=None, **filters):
    """Admins see the queue; everyone else sees only their own disputes."""
    if user.role == ADMIN and scope == "all":
        return grievance_repository.search(**filters)
    if scope == "against_me":
        filters["against_user_id"] = user.id
    else:
        filters["raised_by_user_id"] = user.id
    return grievance_repository.search(**filters)


def update_grievance_status(user, grievance_id, status, resolution=None):
    """
    Move a grievance along.

    Resolving is an administrator action - a respondent cannot close a
    complaint made against them - but the person who raised it may withdraw it.
    """
    grievance = grievance_repository.find_by_id(grievance_id)
    if not grievance:
        raise NotFoundError("Grievance not found.")
    status = status.upper()
    if status not in STATUSES:
        raise ValidationError(f"'status' must be one of: {', '.join(STATUSES)}.")

    if status == "WITHDRAWN":
        if grievance.raised_by_user_id != user.id and user.role != ADMIN:
            raise ForbiddenError("Only the person who raised this grievance can withdraw it.")
    elif user.role != ADMIN:
        raise ForbiddenError("Only an administrator can update a grievance's status.")

    allowed = STATUS_FLOW.get(grievance.status, ())
    if status not in allowed:
        raise ConflictError(
            f"A '{grievance.status}' grievance cannot move to '{status}'. "
            f"Allowed next steps: {', '.join(allowed) if allowed else 'none'}."
        )
    if status in ("RESOLVED", "REJECTED") and not resolution:
        raise ValidationError("Provide a 'resolution' when closing a grievance.")

    if status in CLOSED_STATUSES:
        grievance_repository.resolve(grievance_id, status, resolution, user.id)
    else:
        grievance_repository.update(
            grievance_id, {"status": status, "handled_by_user_id": user.id}
        )

    if grievance.against_user_id:
        buyer = buyer_profile_repository.find_by_user_id(grievance.against_user_id)
        if buyer:
            recalculate_buyer_trust(buyer.id)
    return grievance_repository.detail(grievance_id)


def grievance_dashboard():
    """Counts for the admin queue."""
    open_items, open_total = grievance_repository.search(status="OPEN", page_size=100)
    review_items, review_total = grievance_repository.search(status="UNDER_REVIEW", page_size=100)
    return {
        "open": open_total,
        "under_review": review_total,
        "oldest_open": open_items[0].to_dict() if open_items else None,
        "as_of": dt.date.today().isoformat(),
    }
