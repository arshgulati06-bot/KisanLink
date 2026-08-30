"""
Distance and location helpers.

No external mapping API is called. The project documentation is explicit that
an unverified API must not become a dependency, so distances here are computed
from stored coordinates with the haversine formula and then multiplied by a
road factor to approximate a driving distance.

Every distance this module returns is therefore an ESTIMATE, and it says so in
the payload. If a real routing API is verified later, only this module changes.
"""
import math

from app.config.settings import settings

EARTH_RADIUS_KM = 6371.0

MEASURED = "MEASURED_STRAIGHT_LINE"
ESTIMATED_FROM_DISTRICT = "ESTIMATED_FROM_DISTRICT"
UNKNOWN = "UNKNOWN"


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres between two coordinate pairs."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    lat1, lon1, lat2, lon2 = map(lambda v: math.radians(float(v)), (lat1, lon1, lat2, lon2))
    d_lat, d_lon = lat2 - lat1, lon2 - lon1
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def road_distance_km(lat1, lon1, lat2, lon2):
    """
    Approximate road distance.

    Straight-line distance understates a real journey, so it is scaled by
    ROAD_DISTANCE_FACTOR (1.3 by default). This is a rule of thumb, not a route.
    """
    straight = haversine_km(lat1, lon1, lat2, lon2)
    if straight is None:
        return None
    return round(straight * settings.ROAD_DISTANCE_FACTOR, 2)


def proximity_bucket(origin, destination):
    """Coarse closeness from administrative fields when coordinates are missing."""
    origin_district = (origin.get("district") or "").strip().lower()
    dest_district = (destination.get("district") or "").strip().lower()
    origin_state = (origin.get("state") or "").strip().lower()
    dest_state = (destination.get("state") or "").strip().lower()
    if origin_district and origin_district == dest_district:
        return "SAME_DISTRICT"
    if origin_state and origin_state == dest_state:
        return "SAME_STATE"
    return "OTHER"


def distance_between(origin, destination):
    """
    Best available distance between two places.

    Args:
        origin, destination: dicts with ``latitude``/``longitude`` and,
            as a fallback, ``district``/``state``.

    Returns:
        dict: ``distance_km`` (None when unknown), ``method``, ``proximity``
        and a plain-language ``note``. Callers must respect ``method`` rather
        than treating every distance as measured.
    """
    distance = road_distance_km(
        origin.get("latitude"),
        origin.get("longitude"),
        destination.get("latitude"),
        destination.get("longitude"),
    )
    proximity = proximity_bucket(origin, destination)
    if distance is not None:
        return {
            "distance_km": distance,
            "method": MEASURED,
            "proximity": proximity,
            "is_estimate": True,
            "note": (
                "Estimated road distance: straight-line distance scaled by "
                f"{settings.ROAD_DISTANCE_FACTOR} to approximate roads."
            ),
        }
    return {
        "distance_km": None,
        "method": ESTIMATED_FROM_DISTRICT if proximity != "OTHER" else UNKNOWN,
        "proximity": proximity,
        "is_estimate": True,
        "note": "Coordinates are not recorded for one of these locations.",
    }


def nearest(origin, candidates, limit=10, max_distance_km=None):
    """
    Sort candidates by distance from ``origin``.

    Candidates without coordinates are kept but pushed to the end, so a nearby
    market with a missing pin does not silently disappear from the farmer's view.
    """
    results = []
    for candidate in candidates or []:
        location = candidate if isinstance(candidate, dict) else candidate.to_dict()
        measurement = distance_between(origin, location)
        if (
            max_distance_km is not None
            and measurement["distance_km"] is not None
            and measurement["distance_km"] > max_distance_km
        ):
            continue
        results.append({**location, **measurement})
    # Measured distances first, then anything we could only place by district.
    # Without the proximity tiebreak a farmer with no coordinates on file would
    # see facilities in far districts listed ahead of ones in their own.
    proximity_rank = {"SAME_DISTRICT": 0, "SAME_STATE": 1, "OTHER": 2}
    results.sort(
        key=lambda item: (
            item["distance_km"] is None,
            item["distance_km"] if item["distance_km"] is not None else 0,
            proximity_rank.get(item.get("proximity"), 3),
        )
    )
    return results[:limit] if limit else results


def resolve_location(*sources):
    """
    Take the first source that actually has coordinates or a district.

    Used to fall back from a lot's own location to the farmer's profile.
    """
    location = {"latitude": None, "longitude": None, "district": None, "state": None}
    for source in sources:
        if not source:
            continue
        data = source if isinstance(source, dict) else source.to_dict()
        if location["latitude"] is None and data.get("latitude") is not None:
            location["latitude"] = data.get("latitude")
            location["longitude"] = data.get("longitude")
        if not location["district"] and data.get("district"):
            location["district"] = data.get("district")
        if not location["state"] and data.get("state"):
            location["state"] = data.get("state")
    return location
