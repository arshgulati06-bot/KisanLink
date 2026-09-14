"""
Deterministic transport and net-realisation estimates.

This is NOT GPS / live routing. Distances use published approximate
district coordinates (or a state-capital fallback). Transport rupees
use a documented ₹/QTL/km rate typical of hired truck movement.
"""
from __future__ import annotations

import hashlib
import math
import os
from typing import Optional

# Freight is modelled as a two-part tariff, because a single flat ₹/QTL/km
# figure is wrong at both ends of the range: it under-charges a 5 km cart trip
# (where loading, unloading and waiting dominate) and wildly over-charges a
# 300 km haul (where a full truck spreads its cost over the whole load). A
# flat ₹8/QTL/km, for example, put ₹60,000 of "freight" on ₹48,000 of onions.
#
#   cost per quintal = TRANSPORT_LOADING_PER_QTL + TRANSPORT_RATE_PER_QTL_KM × km
#
# Defaults sit inside the range implied by hired-truck rates for agricultural
# produce in India (roughly ₹150–₹450 per quintal for 100–350 km, inclusive of
# loading). Both parts are planning estimates, not a quoted or official tariff,
# and both are overridable from the environment.
TRANSPORT_RATE_PER_QTL_KM = float(os.environ.get("TRANSPORT_RATE_PER_QTL_KM", "1.2") or 1.2)
# Fixed per-quintal cost of a trip regardless of distance (loading, unloading,
# waiting, and the minimum a transporter will accept for turning up).
TRANSPORT_LOADING_PER_QTL = float(os.environ.get("TRANSPORT_LOADING_PER_QTL", "25") or 25)
# Local cartage inside the same market / district.
MIN_TRIP_KM = 12.0
SAME_DISTRICT_KM = 28.0
HANDLING_PER_QTL = 15.0
MANDI_FEE_FRACTION = 0.01  # labelled estimate, not a statutory invoice

# Approximate centroids (lat, lon) for high-volume agri districts.
DISTRICT_COORDS = {
    ("maharashtra", "nashik"): (20.0110, 73.7903),
    ("maharashtra", "pune"): (18.5204, 73.8567),
    ("maharashtra", "mumbai"): (19.0760, 72.8777),
    ("maharashtra", "nagpur"): (21.1458, 79.0882),
    ("maharashtra", "ahmednagar"): (19.0948, 74.7480),
    ("maharashtra", "solapur"): (17.6599, 75.9064),
    ("maharashtra", "satara"): (17.6805, 74.0183),
    ("maharashtra", "sangli"): (16.8524, 74.5815),
    ("maharashtra", "kolhapur"): (16.7050, 74.2433),
    ("maharashtra", "jalgaon"): (21.0077, 75.5626),
    ("karnataka", "bengaluru"): (12.9716, 77.5946),
    ("karnataka", "belgaum"): (15.8497, 74.4977),
    ("karnataka", "hubli"): (15.3647, 75.1240),
    ("karnataka", "mysore"): (12.2958, 76.6394),
    ("gujarat", "ahmedabad"): (23.0225, 72.5714),
    ("gujarat", "rajkot"): (22.3039, 70.8022),
    ("gujarat", "surat"): (21.1702, 72.8311),
    ("delhi", "delhi"): (28.6139, 77.2090),
    ("nct of delhi", "delhi"): (28.6139, 77.2090),
    ("uttar pradesh", "lucknow"): (26.8467, 80.9462),
    ("uttar pradesh", "agra"): (27.1767, 78.0081),
    ("rajasthan", "jaipur"): (26.9124, 75.7873),
    ("rajasthan", "kota"): (25.2138, 75.8648),
    ("madhya pradesh", "indore"): (22.7196, 75.8577),
    ("madhya pradesh", "bhopal"): (23.2599, 77.4126),
    ("west bengal", "kolkata"): (22.5726, 88.3639),
    ("west bengal", "durgapur"): (23.5204, 87.3119),
    ("punjab", "ludhiana"): (30.9010, 75.8573),
    ("punjab", "amritsar"): (31.6340, 74.8723),
    ("haryana", "karnal"): (29.6857, 76.9905),
    ("haryana", "hisar"): (29.1492, 75.7217),
    ("tamil nadu", "chennai"): (13.0827, 80.2707),
    ("andhra pradesh", "guntur"): (16.3067, 80.4365),
    ("telangana", "hyderabad"): (17.3850, 78.4867),
    ("bihar", "patna"): (25.5941, 85.1376),
    ("odisha", "bhubaneswar"): (20.2961, 85.8245),
    ("assam", "guwahati"): (26.1445, 91.7362),
    ("kerala", "ernakulam"): (9.9816, 76.2999),
}

STATE_CAPITALS = {
    "maharashtra": (19.0760, 72.8777),
    "karnataka": (12.9716, 77.5946),
    "gujarat": (23.0225, 72.5714),
    "uttar pradesh": (26.8467, 80.9462),
    "rajasthan": (26.9124, 75.7873),
    "madhya pradesh": (23.2599, 77.4126),
    "west bengal": (22.5726, 88.3639),
    "punjab": (30.7333, 76.7794),
    "haryana": (30.7333, 76.7794),
    "tamil nadu": (13.0827, 80.2707),
    "andhra pradesh": (16.5062, 80.6480),
    "telangana": (17.3850, 78.4867),
    "bihar": (25.5941, 85.1376),
    "odisha": (20.2961, 85.8245),
    "assam": (26.1445, 91.7362),
    "kerala": (8.5241, 76.9366),
    "delhi": (28.6139, 77.2090),
    "nct of delhi": (28.6139, 77.2090),
}


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def transport_rate() -> float:
    """Per-quintal, per-kilometre haul component of the two-part tariff."""
    try:
        return float(
            os.environ.get("TRANSPORT_RATE_PER_QTL_KM", str(TRANSPORT_RATE_PER_QTL_KM))
            or TRANSPORT_RATE_PER_QTL_KM
        )
    except (TypeError, ValueError):
        return 1.2


def transport_loading_rate() -> float:
    """Fixed per-quintal component charged once per trip, whatever the distance."""
    try:
        return float(
            os.environ.get("TRANSPORT_LOADING_PER_QTL", str(TRANSPORT_LOADING_PER_QTL))
            or TRANSPORT_LOADING_PER_QTL
        )
    except (TypeError, ValueError):
        return 25.0


def transport_cost_per_qtl(distance_km: float, rate_per_qtl_km: Optional[float] = None) -> float:
    """Estimated freight for one quintal over `distance_km`, as a two-part tariff."""
    km = max(0.0, float(distance_km or 0))
    rate = float(rate_per_qtl_km if rate_per_qtl_km is not None else transport_rate())
    return transport_loading_rate() + rate * km


def verified_district_coords(state: str, district: str):
    """Return published centroid only. None if the district is not in the table."""
    key = (_norm(state), _norm(district))
    if key in DISTRICT_COORDS:
        lat, lon = DISTRICT_COORDS[key]
        return lat, lon, "published_district_centroid"
    return None


def _lookup_point(state: str, district: str) -> tuple[float, float, str]:
    verified = verified_district_coords(state, district)
    if verified:
        return verified
    key = (_norm(state), _norm(district))
    capital = STATE_CAPITALS.get(_norm(state), (22.0, 78.0))
    digest = hashlib.sha256(f"{key[0]}|{key[1]}".encode()).digest()
    dlat = (digest[0] / 255.0 - 0.5) * 1.6
    dlon = (digest[1] / 255.0 - 0.5) * 1.6
    return capital[0] + dlat, capital[1] + dlon, "state_capital_offset_estimate"


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def estimate_distance_km(origin_state, origin_district, dest_state, dest_district,
                         same_market: bool = False) -> dict:
    if same_market:
        return {
            "km": MIN_TRIP_KM,
            "method": "local_cartage_same_market",
            "note": "Same APMC — local cartage estimate only, not GPS routing.",
        }
    if _norm(origin_state) == _norm(dest_state) and _norm(origin_district) == _norm(dest_district):
        return {
            "km": SAME_DISTRICT_KM,
            "method": "same_district_default",
            "note": "Same district — typical intra-district haul, not GPS routing.",
        }
    o_lat, o_lon, o_src = _lookup_point(origin_state, origin_district)
    d_lat, d_lon, d_src = _lookup_point(dest_state, dest_district)
    km = max(MIN_TRIP_KM, haversine_km(o_lat, o_lon, d_lat, d_lon))
    return {
        "km": round(km, 1),
        "method": "haversine_district_centroids",
        "origin_point": o_src,
        "dest_point": d_src,
        "note": "Straight-line estimate between approximate district points. Not live GPS routing.",
    }


def net_realisation(price_per_qtl: float, quantity_qtl: float, distance_km: float,
                    rate_per_qtl_km: Optional[float] = None) -> dict:
    qty = max(0.0, float(quantity_qtl or 0))
    price = max(0.0, float(price_per_qtl or 0))
    rate = float(rate_per_qtl_km if rate_per_qtl_km is not None else transport_rate())
    km = max(0.0, float(distance_km or 0))
    gross = price * qty
    per_qtl_freight = transport_cost_per_qtl(km, rate)
    transport = per_qtl_freight * qty
    handling = HANDLING_PER_QTL * qty
    mandi_fee = gross * MANDI_FEE_FRACTION
    net = gross - transport - handling - mandi_fee
    return {
        "quantity_qtl": round(qty, 2),
        "price_per_qtl": round(price, 2),
        "gross_sale_value": round(gross, 2),
        "distance_km": round(km, 1),
        "transport_rate_per_qtl_km": rate,
        "transport_loading_per_qtl": round(transport_loading_rate(), 2),
        "transport_cost_per_qtl": round(per_qtl_freight, 2),
        "transport_cost": round(transport, 2),
        "handling_cost": round(handling, 2),
        "mandi_fee_estimate": round(mandi_fee, 2),
        "net_realisation": round(net, 2),
        "cost_note": (
            f"Transport ≈ ₹{transport_loading_rate():.0f}/QTL loading + "
            f"₹{rate:.2f}/QTL/km × {km:.0f} km = ₹{per_qtl_freight:.0f}/QTL (estimate). "
            f"Handling ₹{HANDLING_PER_QTL:.0f}/QTL. Mandi fee ~{MANDI_FEE_FRACTION*100:.0f}% of gross. "
            "Not an invoice."
        ),
    }
