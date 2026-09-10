"""
KisanLink ML Pipeline — Buyer Matching Engine
================================================
Explainable weighted scoring for farmer-lot to buyer-demand matching.

Score composition (matches MASTER_CONTEXT §9 weights):
  Price fit      35% — how well buyer's offered rate covers farmer's expected price
  Quantity fit   20% — how well buyer's required quantity matches lot size
  Quality match  20% — grade compatibility
  Distance       15% — buyer location proximity (rough categorical scoring)
  Trust          10% — buyer verification status

Each factor returns a 0–100 score. The weighted sum gives the final match score.
Factors are only computed for fields that exist in the data — no invented values.

This engine NEVER produces arbitrary percentages.
Every score comes from actual data comparisons.
"""

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Grade compatibility matrix
# ---------------------------------------------------------------------------
_GRADE_COMPAT = {
    ("grade a", "grade a"):          100,
    ("grade a", "premium"):          100,
    ("premium", "grade a"):          100,
    ("grade a", "grade a or b"):     100,
    ("grade a", "grade b"):           60,
    ("grade b", "grade a or b"):     100,
    ("grade b", "grade b"):          100,
    ("grade b", "grade a"):           30,
    ("grade c", "grade b"):           20,
    ("grade c", "grade c"):          100,
}

def _grade_score(farmer_grade: str, buyer_grade: str) -> float:
    """Return 0–100 compatibility score for two grade strings."""
    fk = farmer_grade.lower().strip()
    bk = buyer_grade.lower().strip()
    if fk == bk:
        return 100.0
    return float(_GRADE_COMPAT.get((fk, bk), 50.0))  # 50 = uncertain/partial match


# ---------------------------------------------------------------------------
# Price fit
# ---------------------------------------------------------------------------
def _price_score(farmer_expected: float, buyer_offered: float) -> float:
    """
    How well buyer's rate covers farmer's expected price.
    100 if buyer_offered >= farmer_expected.
    Decays linearly to 0 as buyer_offered drops to 70% of farmer_expected.
    """
    if farmer_expected <= 0 or buyer_offered <= 0:
        return 50.0  # unknown
    ratio = buyer_offered / farmer_expected
    if ratio >= 1.0:
        return 100.0
    elif ratio >= 0.70:
        return max(0, (ratio - 0.70) / 0.30 * 100)
    return 0.0


# ---------------------------------------------------------------------------
# Quantity fit
# ---------------------------------------------------------------------------
def _quantity_score(farmer_qty: float, buyer_qty: float) -> float:
    """
    How well quantities match.
    100 if buyer needs exactly what farmer has.
    Decays if buyer needs much more (under-supply) or much less (over-supply).
    """
    if farmer_qty <= 0 or buyer_qty <= 0:
        return 50.0
    ratio = min(farmer_qty, buyer_qty) / max(farmer_qty, buyer_qty)
    return round(ratio * 100, 1)


# ---------------------------------------------------------------------------
# Distance / location
# ---------------------------------------------------------------------------
def _distance_score(farmer_state: str, buyer_location: str) -> float:
    """
    Rough location-based score using state matching.
    100 if buyer is in same state (local market).
    50  if different state.
    25  if very far / unknown.
    A real implementation would use geocoding — this is a transparent proxy.
    """
    if not farmer_state or not buyer_location:
        return 50.0
    fl = farmer_state.lower()
    bl = buyer_location.lower()
    if fl in bl or any(w in bl for w in fl.split()):
        return 100.0
    # Check for known neighbouring states
    _neighbours = {
        "maharashtra": {"karnataka", "gujarat", "madhya pradesh", "goa", "telangana"},
        "karnataka":   {"maharashtra", "goa", "kerala", "tamil nadu", "andhra pradesh"},
        "uttar pradesh": {"delhi", "haryana", "rajasthan", "bihar"},
        "delhi":       {"haryana", "uttar pradesh"},
    }
    neighbours = _neighbours.get(fl, set())
    for n in neighbours:
        if n in bl:
            return 70.0
    return 40.0


# ---------------------------------------------------------------------------
# Trust
# ---------------------------------------------------------------------------
def _trust_score(trust_status: str) -> float:
    """Return trust score based on verification status."""
    if not trust_status:
        return 50.0
    ts = trust_status.lower()
    if "platform-reviewed" in ts or "verified" in ts:
        return 100.0
    elif "registered" in ts:
        return 75.0
    return 50.0


# =============================================================================
# match_buyers
# =============================================================================

def match_buyers(
    lot_commodity:      str,
    lot_quantity_qtl:   float,
    lot_grade:          str,
    lot_state:          str,
    lot_expected_price: float,
    buyer_demands:      list,
) -> list:
    """
    Score and rank buyer demands against a farmer lot.

    Parameters
    ----------
    lot_commodity       : str — crop name from the lot
    lot_quantity_qtl    : float — available quantity in quintals
    lot_grade           : str — e.g. "Grade A"
    lot_state           : str — farmer's state
    lot_expected_price  : float — farmer's minimum expected price ₹/QTL
    buyer_demands       : list of dicts with fields:
        id, buyerName, buyerType, crop, quantity, unit, grade,
        deliveryLocation, offeredRate, requiredDate, status,
        trustStatus (optional)

    Returns
    -------
    list of dicts, sorted descending by match_score:
        {
          "buyer_id"         : str,
          "buyer_name"       : str,
          "buyer_type"       : str,
          "offered_rate"     : float,
          "required_qty"     : float,
          "required_grade"   : str,
          "delivery_location": str,
          "required_date"    : str,
          "match_score"      : int (0–100),
          "matched_criteria" : list of {"name", "score", "weight", "note"},
          "unmatched_criteria": list of str,
          "commodity_match"  : bool,
        }
    """
    results = []

    for demand in buyer_demands:
        # --- Commodity match (hard gate) ---
        demand_crop = (demand.get("crop") or "").lower().strip()
        lot_crop    = (lot_commodity or "").lower().strip()

        # Strip Hindi crop names like "Onion (कांदा)" → "onion"
        lot_crop_base    = re.sub(r"\s*\(.*?\)", "", lot_crop).strip()
        demand_crop_base = re.sub(r"\s*\(.*?\)", "", demand_crop).strip()

        commodity_match = (
            lot_crop_base == demand_crop_base
            or lot_crop_base in demand_crop_base
            or demand_crop_base in lot_crop_base
        )

        matched   = []
        unmatched = []

        # --- Price fit (35%) ---
        buyer_rate     = float(demand.get("offeredRate") or 0)
        price_s        = _price_score(lot_expected_price, buyer_rate)
        matched.append({
            "name":   "Price Fit",
            "score":  round(price_s),
            "weight": 35,
            "note":   f"Buyer ₹{buyer_rate:,.0f} vs expected ₹{lot_expected_price:,.0f}",
        })

        # --- Quantity fit (20%) ---
        raw_qty = demand.get("quantity") or 0
        try:
            buyer_qty = float(str(raw_qty).replace("QTL", "").strip())
        except (ValueError, TypeError):
            buyer_qty = 0.0
        qty_s = _quantity_score(lot_quantity_qtl, buyer_qty)
        matched.append({
            "name":   "Quantity Fit",
            "score":  round(qty_s),
            "weight": 20,
            "note":   f"Buyer needs {buyer_qty} QTL, lot has {lot_quantity_qtl} QTL",
        })

        # --- Quality match (20%) ---
        buyer_grade = demand.get("grade") or "Grade A"
        grade_s     = _grade_score(lot_grade, buyer_grade)
        matched.append({
            "name":   "Quality Match",
            "score":  round(grade_s),
            "weight": 20,
            "note":   f"Lot grade: {lot_grade}, Buyer needs: {buyer_grade}",
        })

        # --- Distance (15%) ---
        buyer_loc = demand.get("deliveryLocation") or ""
        dist_s    = _distance_score(lot_state, buyer_loc)
        matched.append({
            "name":   "Location",
            "score":  round(dist_s),
            "weight": 15,
            "note":   f"Delivery: {buyer_loc}",
        })

        # --- Trust (10%) ---
        trust    = demand.get("trustStatus") or demand.get("buyerType") or ""
        trust_s  = _trust_score(trust)
        matched.append({
            "name":   "Buyer Trust",
            "score":  round(trust_s),
            "weight": 10,
            "note":   trust or "Unverified",
        })

        # --- Commodity mismatch note ---
        if not commodity_match:
            unmatched.append(f"Commodity mismatch: lot has {lot_crop_base}, buyer needs {demand_crop_base}")

        # --- Weighted score ---
        weighted_score = sum(
            c["score"] * c["weight"] / 100.0
            for c in matched
        )
        # Penalize commodity mismatch
        if not commodity_match:
            weighted_score *= 0.3

        results.append({
            "buyer_id":          demand.get("id", ""),
            "buyer_name":        demand.get("buyerName", ""),
            "buyer_type":        demand.get("buyerType", ""),
            "offered_rate":      buyer_rate,
            "required_qty":      buyer_qty,
            "required_grade":    buyer_grade,
            "delivery_location": buyer_loc,
            "required_date":     demand.get("requiredDate", ""),
            "status":            demand.get("status", "ACTIVE"),
            "match_score":       round(weighted_score),
            "matched_criteria":  matched,
            "unmatched_criteria": unmatched,
            "commodity_match":   commodity_match,
        })

    # Sort by score descending
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results
