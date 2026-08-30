"""
Transaction records and payment tracking.

Two commitments shape this module:

* the record is **transparent** - every status change is written to an
  append-only history with who made it and when;
* the record is **honest about money** - gross and net are stored separately,
  with each deduction itemised, so nobody can read the headline price as what
  the farmer received.

No payment gateway is integrated. Payments are recorded as the parties report
them, which is enough to make reliability visible without pretending to settle
funds.
"""
import datetime as dt

from app.models.buyer_requirement import BUYER_PAYS_TRANSPORT
from app.models.transaction import (
    ACCEPTED,
    COMPLETED,
    DELIVERED,
    PAID,
    PAYMENT_PENDING,
    STATUS_FLOW,
    STATUSES,
)
from app.models.user import ADMIN
from app.repositories.lot_repository import lot_contribution_repository, lot_repository
from app.repositories.transaction_repository import (
    payment_repository,
    transaction_repository,
    transaction_status_history_repository,
)
from app.repositories.user_repository import buyer_profile_repository
from app.services import logistics_service, maps_service
from app.utils.responses import ConflictError, ForbiddenError, NotFoundError, ValidationError


def create_from_offer(offer, user):
    """
    Open a transaction from an accepted offer.

    Costs are estimated at acceptance time and stored, so the net figure the
    farmer agreed to is preserved even if the cost model changes later.
    """
    existing = transaction_repository.find_by_offer(offer.id)
    if existing:
        return transaction_repository.detail(existing.id)

    lot = lot_repository.find_by_id(offer.lot_id)
    buyer = buyer_profile_repository.find_by_id(offer.buyer_id)

    gross = float(offer.price_per_unit) * float(offer.quantity)
    transport_cost = _estimate_transport(lot, buyer, offer)
    commission = 0.0  # A direct sale carries no mandi commission.
    net = gross - transport_cost - commission

    payment_terms = int(offer.payment_terms_days or 7)
    transaction_id = transaction_repository.insert(
        {
            "transaction_code": transaction_repository.next_code(),
            "offer_id": offer.id,
            "lot_id": offer.lot_id,
            "buyer_id": offer.buyer_id,
            "seller_user_id": offer.seller_user_id,
            "crop_id": lot.crop_id,
            "quantity": float(offer.quantity),
            "unit": offer.unit,
            "price_per_unit": float(offer.price_per_unit),
            "gross_amount": round(gross, 2),
            "transport_cost": round(transport_cost, 2),
            "storage_cost": 0,
            "commission_cost": round(commission, 2),
            "other_deductions": 0,
            "net_amount": round(net, 2),
            "status": ACCEPTED,
            "expected_delivery_date": _expected_delivery_date(offer),
        }
    )
    transaction_status_history_repository.log(
        transaction_id, None, ACCEPTED, user.id, "Offer accepted by the seller."
    )
    # The payment obligation is created up front so it can go overdue, which is
    # what makes payment reliability measurable at all.
    payment_repository.insert(
        {
            "transaction_id": transaction_id,
            "amount": round(gross, 2),
            "mode": "BANK_TRANSFER",
            "status": "PENDING",
            "due_date": (dt.date.today() + dt.timedelta(days=payment_terms)).isoformat(),
            "remarks": f"Payment due {payment_terms} days from acceptance.",
        }
    )
    buyer_profile_repository.refresh_transaction_counters(offer.buyer_id)
    return transaction_repository.detail(transaction_id)


def _estimate_transport(lot, buyer, offer):
    """Whoever carries the transport cost, only the farmer's share is deducted."""
    borne_by = (offer.transport_borne_by or "FARMER").upper()
    if borne_by == "BUYER" or (offer.delivery_mode or "") in BUYER_PAYS_TRANSPORT:
        return 0.0
    measurement = maps_service.distance_between(
        {
            "latitude": lot.latitude,
            "longitude": lot.longitude,
            "district": lot.district,
            "state": lot.state,
        },
        {
            "latitude": buyer.latitude if buyer else None,
            "longitude": buyer.longitude if buyer else None,
            "district": buyer.district if buyer else None,
            "state": buyer.state if buyer else None,
        },
    )
    estimate = logistics_service.estimate_transport(
        offer.quantity, offer.unit, measurement["distance_km"]
    )
    return float(estimate.get("estimated_cost") or 0.0)


def _expected_delivery_date(offer):
    if offer.valid_until:
        return str(offer.valid_until)[:10]
    return (dt.date.today() + dt.timedelta(days=7)).isoformat()


def get_transaction(transaction_id, viewer=None):
    detail = transaction_repository.detail(transaction_id)
    if not detail:
        raise NotFoundError("Transaction not found.")
    if viewer is not None:
        _assert_party(viewer, transaction_repository.find_by_id(transaction_id))
        detail["is_seller"] = detail["seller_user_id"] == viewer.id
    detail["history"] = transaction_status_history_repository.for_transaction(transaction_id)
    detail["payments"] = [p.to_dict() for p in payment_repository.for_transaction(transaction_id)]
    detail["amount_outstanding"] = round(
        float(detail.get("gross_amount") or 0) - payment_repository.total_paid(transaction_id), 2
    )
    detail["next_statuses"] = list(STATUS_FLOW.get(detail["status"], ()))
    return detail


def list_transactions(viewer, role_scope=None, **filters):
    """Scoped to the caller: a farmer sees their sales, a buyer their purchases."""
    if viewer.role == ADMIN and role_scope == "all":
        return transaction_repository.search(**filters)
    buyer = buyer_profile_repository.find_by_user_id(viewer.id)
    if buyer and role_scope != "seller":
        filters["buyer_id"] = buyer.id
    else:
        filters["seller_user_id"] = viewer.id
    return transaction_repository.search(**filters)


def update_status(user, transaction_id, new_status, remarks=None):
    """
    Advance a transaction, recording who moved it and why.

    Only the moves declared in ``STATUS_FLOW`` are allowed, so the history can
    be trusted as a real sequence of events rather than a free-text field.
    """
    transaction = transaction_repository.find_by_id(transaction_id)
    if not transaction:
        raise NotFoundError("Transaction not found.")
    _assert_party(user, transaction)

    new_status = new_status.upper()
    if new_status not in STATUSES:
        raise ValidationError(f"'status' must be one of: {', '.join(STATUSES)}.")
    allowed = STATUS_FLOW.get(transaction.status, ())
    if new_status not in allowed:
        raise ConflictError(
            f"A transaction at '{transaction.status}' cannot move to '{new_status}'. "
            f"Allowed next steps: {', '.join(allowed) if allowed else 'none'}."
        )

    payload = {"status": new_status}
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if new_status == DELIVERED:
        payload["delivered_at"] = now
    if new_status == COMPLETED:
        payload["completed_at"] = now

    transaction_repository.update(transaction_id, payload)
    transaction_status_history_repository.log(
        transaction_id, transaction.status, new_status, user.id, remarks
    )

    if new_status == COMPLETED:
        _on_completed(transaction)
    return get_transaction(transaction_id)


def _on_completed(transaction):
    """Housekeeping once a deal closes: counters, trust, and FPO payouts."""
    from app.services import trust_service

    buyer_profile_repository.refresh_transaction_counters(transaction.buyer_id)
    trust_service.recalculate_buyer_trust(transaction.buyer_id)

    lot = lot_repository.find_by_id(transaction.lot_id)
    if lot and lot.is_aggregated:
        lot_contribution_repository.record_payouts(lot.id, float(transaction.net_amount or 0))


def record_payment(user, transaction_id, data):
    """
    Record a payment against a transaction.

    When the recorded payments cover the gross amount, the transaction is
    advanced to PAID automatically - the money moving is the event, not a
    separate button press.
    """
    transaction = transaction_repository.find_by_id(transaction_id)
    if not transaction:
        raise NotFoundError("Transaction not found.")
    _assert_party(user, transaction)

    amount = float(data["amount"])
    if amount <= 0:
        raise ValidationError("'amount' must be greater than zero.")
    already_paid = payment_repository.total_paid(transaction_id)
    if already_paid + amount > float(transaction.gross_amount) + 0.01:
        raise ValidationError(
            f"This payment would exceed the transaction value. "
            f"Outstanding: Rs {float(transaction.gross_amount) - already_paid:,.2f}."
        )

    paid_at = data.get("paid_at") or dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payment_id = _settle_against_obligation(transaction_id, amount, paid_at, user, data)

    total_paid = payment_repository.total_paid(transaction_id)
    if total_paid >= float(transaction.gross_amount) - 0.01:
        if transaction.status == DELIVERED:
            update_status(user, transaction_id, PAYMENT_PENDING, "Payment recorded.")
        if transaction.status in (DELIVERED, PAYMENT_PENDING):
            update_status(user, transaction_id, PAID, "Payment received in full.")

    from app.services import trust_service

    trust_service.recalculate_buyer_trust(transaction.buyer_id)
    return payment_repository.find_by_id(payment_id).to_dict()


def _settle_against_obligation(transaction_id, amount, paid_at, user, data):
    """
    Apply a payment to the obligation raised when the offer was accepted.

    The obligation row created at acceptance IS the payment record - settling
    it must update that row, not add a second one, or the transaction would
    appear paid twice. A part payment splits the row: the paid portion becomes
    a PAID record and the balance stays outstanding under the same due date.
    """
    outstanding = [
        payment
        for payment in payment_repository.for_transaction(transaction_id)
        if payment.status in ("PENDING", "PARTIAL")
    ]
    common = {
        "mode": data.get("mode", "BANK_TRANSFER"),
        "reference_no": data.get("reference_no"),
        "recorded_by_user_id": user.id,
        "remarks": data.get("remarks"),
        "paid_at": paid_at,
        "status": data.get("status", "PAID"),
    }

    if not outstanding:
        # No obligation on file (an unexpected extra payment): record it as-is.
        return payment_repository.insert(
            {"transaction_id": transaction_id, "amount": round(amount, 2),
             "due_date": data.get("due_date"), **common}
        )

    obligation = outstanding[0]
    obligation_amount = float(obligation.amount or 0)

    if amount >= obligation_amount - 0.01:
        payment_repository.update(obligation.id, {"amount": round(amount, 2), **common})
        return obligation.id

    payment_repository.update(
        obligation.id,
        {
            "amount": round(obligation_amount - amount, 2),
            "status": "PARTIAL",
            "remarks": f"Balance outstanding after a part payment of Rs {amount:,.2f}.",
        },
    )
    return payment_repository.insert(
        {
            "transaction_id": transaction_id,
            "amount": round(amount, 2),
            "due_date": obligation.due_date,
            **common,
        }
    )


def transaction_history(transaction_id, viewer=None):
    transaction = transaction_repository.find_by_id(transaction_id)
    if not transaction:
        raise NotFoundError("Transaction not found.")
    if viewer is not None:
        _assert_party(viewer, transaction)
    return transaction_status_history_repository.for_transaction(transaction_id)


def summary_for(user):
    """Dashboard totals, from whichever side of the deal the caller is on."""
    buyer = buyer_profile_repository.find_by_user_id(user.id)
    if buyer:
        return transaction_repository.party_summary(buyer_id=buyer.id)
    return transaction_repository.party_summary(seller_user_id=user.id)


def net_realization_breakdown(transaction_id, viewer=None):
    """
    Show exactly how the gross became the net.

    This is the record that makes "improved price realization" checkable rather
    than a claim.
    """
    transaction = transaction_repository.find_by_id(transaction_id)
    if not transaction:
        raise NotFoundError("Transaction not found.")
    if viewer is not None:
        _assert_party(viewer, transaction)
    gross = float(transaction.gross_amount or 0)
    deductions = {
        "transport": float(transaction.transport_cost or 0),
        "storage": float(transaction.storage_cost or 0),
        "commission": float(transaction.commission_cost or 0),
        "other": float(transaction.other_deductions or 0),
    }
    total = sum(deductions.values())
    quantity = float(transaction.quantity or 0)
    return {
        "transaction_code": transaction.transaction_code,
        "quantity": quantity,
        "unit": transaction.unit,
        "gross_price_per_unit": float(transaction.price_per_unit or 0),
        "gross_amount": round(gross, 2),
        "deductions": {k: round(v, 2) for k, v in deductions.items()},
        "total_deductions": round(total, 2),
        "net_amount": round(gross - total, 2),
        "net_price_per_unit": round((gross - total) / quantity, 2) if quantity else None,
        "deduction_percent": round(100.0 * total / gross, 2) if gross else 0.0,
        "note": (
            "Transport and storage figures are KisanLink cost estimates recorded when the "
            "offer was accepted, not invoiced amounts."
        ),
    }


def overdue_payments(buyer_id=None):
    return payment_repository.overdue_for_buyer(buyer_id, dt.date.today().isoformat())


def _assert_party(user, transaction):
    if user.role == ADMIN or transaction.seller_user_id == user.id:
        return
    buyer = buyer_profile_repository.find_by_user_id(user.id)
    if buyer and buyer.id == transaction.buyer_id:
        return
    raise ForbiddenError("You are not a party to this transaction.")
