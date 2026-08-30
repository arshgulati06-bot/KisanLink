"""
Explainable weighted matching between a lot and a buying opportunity.

This is deliberately NOT a machine-learned ranker. A 10-day prototype has no
transaction history to learn from, and a farmer being told to accept a lower
price deserves to see the arithmetic. Every component below produces a score in
0..1, a weight, and a sentence explaining itself.

Weights come from ``app/config/settings.py`` and are meant to be tuned.
"""

#: Ordinal value of each self-declared grade. Higher is better.
GRADE_RANK = {"A": 3, "B": 2, "C": 1}

#: Platform verification maps onto a trust component of its own.
#:
#: The first four apply to buyer accounts. The last two apply to market
#: channels (mandis), where the counterparty is a marketplace rather than a
#: named buyer: a regulated APMC or eNAM yard scores well because the payment
#: mechanism is governed, not because KisanLink reviewed anyone.
VERIFICATION_TRUST = {
    "PLATFORM_REVIEWED": 1.00,
    "DOCUMENTS_SUBMITTED": 0.60,
    "UNVERIFIED": 0.30,
    "REJECTED": 0.00,
    "REGULATED_MARKET": 0.85,
    "PRIVATE_MARKET": 0.55,
}

#: How each of the above reads in an explanation line.
TRUST_STATUS_LABELS = {
    "REGULATED_MARKET": "Regulated market yard (APMC/eNAM)",
    "PRIVATE_MARKET": "Private market",
}

#: Fallback distance scores when we have no coordinates for one of the parties.
#: Flagged as estimated so the UI never shows them as a measured distance.
DISTRICT_PROXIMITY_SCORE = {"SAME_DISTRICT": 0.80, "SAME_STATE": 0.45, "OTHER": 0.20}


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def grade_rank(grade):
    return GRADE_RANK.get(str(grade or "").strip().upper(), 0)


# ---------------------------------------------------------------------------
# Individual components
# ---------------------------------------------------------------------------
def score_price(offered_price, benchmark_price):
    """
    How good the price is against the prevailing market price.

    A price equal to the market benchmark scores 0.5. 25% above the benchmark
    scores 1.0, 25% below scores 0.0. Anchoring at the benchmark rather than at
    the best offer in the list means a farmer with only poor options still sees
    that they are poor.
    """
    if offered_price is None:
        return {
            "score": 0.0,
            "available": False,
            "reason": "No price quoted by this buyer.",
        }
    if not benchmark_price:
        # No market reference: we can still rank candidates against each other,
        # but we must not claim the price is good or bad in absolute terms.
        return {
            "score": 0.5,
            "available": False,
            "offered_price": round(float(offered_price), 2),
            "reason": "No recent market price available to compare this offer against.",
        }
    ratio = float(offered_price) / float(benchmark_price)
    score = clamp((ratio - 0.75) / 0.5)
    difference_percent = (ratio - 1.0) * 100.0
    if difference_percent >= 2:
        reason = f"Price is {difference_percent:.1f}% above the recent market price."
    elif difference_percent <= -2:
        reason = f"Price is {abs(difference_percent):.1f}% below the recent market price."
    else:
        reason = "Price is close to the recent market price."
    return {
        "score": round(score, 4),
        "available": True,
        "offered_price": round(float(offered_price), 2),
        "benchmark_price": round(float(benchmark_price), 2),
        "difference_percent": round(difference_percent, 2),
        "reason": reason,
    }


def score_quantity(lot_quantity, wanted_quantity):
    """
    How well the two volumes fit each other.

    Scored from both sides: how much of the buyer's requirement this lot covers,
    and how much of the lot the buyer would take. A buyer wanting 10 quintals
    from a 500-quintal lot is a poor match even though they "fit".
    """
    lot_quantity = float(lot_quantity or 0)
    wanted_quantity = float(wanted_quantity or 0)
    if lot_quantity <= 0 or wanted_quantity <= 0:
        return {"score": 0.0, "available": False, "reason": "Quantity not specified."}
    tradeable = min(lot_quantity, wanted_quantity)
    covers_requirement = tradeable / wanted_quantity
    clears_lot = tradeable / lot_quantity
    score = 0.5 * covers_requirement + 0.5 * clears_lot
    if clears_lot >= 0.99 and covers_requirement >= 0.99:
        reason = "Buyer's requirement matches the full lot."
    elif clears_lot >= 0.99:
        reason = f"Buyer can take the entire lot ({covers_requirement * 100:.0f}% of their requirement)."
    else:
        reason = (
            f"Buyer would take {tradeable:,.0f} of {lot_quantity:,.0f} "
            f"({clears_lot * 100:.0f}% of the lot)."
        )
    return {
        "score": round(clamp(score), 4),
        "available": True,
        "lot_quantity": lot_quantity,
        "required_quantity": wanted_quantity,
        "tradeable_quantity": round(tradeable, 2),
        "covers_requirement_percent": round(covers_requirement * 100, 1),
        "clears_lot_percent": round(clears_lot * 100, 1),
        "reason": reason,
    }


def score_quality(lot_grade, required_grade, lot_moisture=None, max_moisture=None):
    """
    Whether the lot meets the buyer's declared specification.

    Grades are self-declared A/B/C in this prototype. Falling short of the
    required grade is treated as a near-blocker rather than a small penalty,
    because a rejected consignment at the buyer's gate is the worst outcome
    for the farmer.
    """
    lot_rank, required_rank = grade_rank(lot_grade), grade_rank(required_grade)
    if not lot_rank or not required_rank:
        return {
            "score": 0.5,
            "available": False,
            "reason": "Grade not specified on one side; quality match could not be checked.",
        }
    gap = required_rank - lot_rank
    blocking = False
    if gap <= 0:
        score, reason = 1.0, f"Lot grade {lot_grade} meets the required grade {required_grade}."
    elif gap == 1:
        score = 0.30
        reason = (
            f"Lot grade {lot_grade} is one grade below the required {required_grade}. "
            "The buyer may reject it or renegotiate."
        )
    else:
        score, blocking = 0.0, True
        reason = f"Lot grade {lot_grade} does not meet the required grade {required_grade}."

    moisture_note = None
    if max_moisture is not None and lot_moisture is not None:
        if float(lot_moisture) > float(max_moisture):
            score *= 0.5
            moisture_note = (
                f"Moisture {float(lot_moisture):.1f}% exceeds the buyer's limit "
                f"of {float(max_moisture):.1f}%."
            )
            reason = f"{reason} {moisture_note}"
        else:
            moisture_note = (
                f"Moisture {float(lot_moisture):.1f}% is within the buyer's limit."
            )

    return {
        "score": round(clamp(score), 4),
        "available": True,
        "lot_grade": lot_grade,
        "required_grade": required_grade,
        "meets_grade": gap <= 0,
        "blocking": blocking,
        "moisture_note": moisture_note,
        "reason": reason,
    }


def score_distance(distance_km, max_distance_km, proximity=None):
    """
    Closeness, scored linearly to zero at ``max_distance_km``.

    When coordinates are missing we fall back to a district/state guess and
    mark the result as estimated rather than dropping the candidate.
    """
    if distance_km is None:
        bucket = proximity or "OTHER"
        return {
            "score": DISTRICT_PROXIMITY_SCORE.get(bucket, 0.20),
            "available": False,
            "estimated_from": bucket,
            "reason": (
                "Exact distance unavailable (location coordinates missing); "
                f"estimated from administrative proximity ({bucket.replace('_', ' ').lower()})."
            ),
        }
    distance_km = float(distance_km)
    score = clamp(1.0 - distance_km / float(max_distance_km))
    return {
        "score": round(score, 4),
        "available": True,
        "distance_km": round(distance_km, 1),
        "reason": f"Approximately {distance_km:.0f} km by road from the lot location.",
    }


def score_trust(verification_status, trust_score=None, on_time_payment_rate=None,
                completed_transactions=0, open_grievances=0):
    """
    Payment reliability and buyer credentials, combined into one component.

    Verification is a platform review status only - it is never presented as
    government KYC or GST verification.
    """
    verification = VERIFICATION_TRUST.get(
        str(verification_status or "UNVERIFIED").upper(), 0.30
    )
    reputation = float(trust_score) / 100.0 if trust_score is not None else 0.40
    score = 0.5 * verification + 0.5 * clamp(reputation)

    if on_time_payment_rate is not None:
        # A poor payment record pulls the score down hard; a good one nudges up.
        punctuality = clamp(float(on_time_payment_rate) / 100.0)
        score = 0.7 * score + 0.3 * punctuality
    if open_grievances:
        score *= max(0.4, 1.0 - 0.2 * int(open_grievances))

    status_key = str(verification_status or "UNVERIFIED").upper()
    if status_key in TRUST_STATUS_LABELS:
        parts = [TRUST_STATUS_LABELS[status_key]]
    else:
        parts = [f"Platform status: {status_key.replace('_', ' ').title()}"]
    if completed_transactions:
        parts.append(f"{int(completed_transactions)} completed transactions on the platform")
    else:
        parts.append("no completed transactions on the platform yet")
    if on_time_payment_rate is not None:
        parts.append(f"{float(on_time_payment_rate):.0f}% of payments made on time")
    else:
        parts.append("no payment history recorded")
    if open_grievances:
        parts.append(f"{int(open_grievances)} open grievance(s)")

    return {
        "score": round(clamp(score), 4),
        "available": True,
        "verification_status": verification_status,
        "on_time_payment_rate": on_time_payment_rate,
        "open_grievances": int(open_grievances or 0),
        "reason": "; ".join(parts) + ".",
    }


# ---------------------------------------------------------------------------
# Combined score
# ---------------------------------------------------------------------------
def score_match(lot, candidate, weights, max_distance_km=300.0, benchmark_price=None):
    """
    Score one buying opportunity against one lot.

    Args:
        lot: dict with ``quantity``, ``grade``, ``moisture_percent``.
        candidate: dict with ``price``, ``required_quantity``, ``min_grade``,
            ``max_moisture_percent``, ``distance_km`` (or ``proximity``), and
            the trust fields. Prices and quantities must already be expressed
            in the lot's unit - conversion is the caller's job.
        weights: mapping of component name to weight, summing to 1.
        max_distance_km: distance at which the distance component hits zero.
        benchmark_price: recent market price in the lot's unit, or None.

    Returns:
        dict: ``total_score`` (0-100), per-component detail, and any blockers.
    """
    components = {
        "price": score_price(candidate.get("price"), benchmark_price),
        "quantity": score_quantity(lot.get("quantity"), candidate.get("required_quantity")),
        "quality": score_quality(
            lot.get("grade"),
            candidate.get("min_grade"),
            lot.get("moisture_percent"),
            candidate.get("max_moisture_percent"),
        ),
        "distance": score_distance(
            candidate.get("distance_km"), max_distance_km, candidate.get("proximity")
        ),
        "trust": score_trust(
            candidate.get("verification_status"),
            candidate.get("trust_score"),
            candidate.get("on_time_payment_rate"),
            candidate.get("completed_transactions", 0),
            candidate.get("open_grievances", 0),
        ),
    }

    total = 0.0
    for name, component in components.items():
        weight = float(weights.get(name, 0.0))
        component["weight"] = round(weight, 4)
        component["weighted_score"] = round(component["score"] * weight, 4)
        component["contribution_percent"] = round(component["score"] * weight * 100, 2)
        total += component["weighted_score"]

    blockers = []
    if components["quality"].get("blocking"):
        blockers.append("Lot grade is below the buyer's minimum requirement.")
    if not components["quantity"]["available"]:
        blockers.append("Quantity is missing on one side of the match.")

    return {
        "total_score": round(clamp(total) * 100, 2),
        "components": components,
        "blockers": blockers,
        "is_viable": not blockers,
    }


def rank_matches(scored_candidates, key="total_score", limit=None):
    """Sort scored candidates best-first, viable ones ahead of blocked ones."""
    ordered = sorted(
        scored_candidates,
        key=lambda item: (item.get("is_viable", True), item.get(key, 0)),
        reverse=True,
    )
    for position, item in enumerate(ordered, start=1):
        item["rank"] = position
    return ordered[:limit] if limit else ordered
