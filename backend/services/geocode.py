"""
Nominatim geocoding (OpenStreetMap). Used only after the user provides
coordinates or a named place. Results are cached; coordinates are not persisted.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

NOMINATIM_BASE = os.environ.get(
    "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"
).rstrip("/")
USER_AGENT = os.environ.get(
    "NOMINATIM_USER_AGENT",
    "KisanLink/1.0 (agricultural decision support; contact via project README)",
)

_CACHE = {}
_LOCK = threading.Lock()
_LAST_CALL = 0.0


def external_http_allowed() -> bool:
    flag = os.environ.get("KISANLINK_DISABLE_EXTERNAL", "").strip().lower()
    return flag not in {"1", "true", "yes"}


def validate_coords(lat, lon) -> tuple[Optional[float], Optional[float], Optional[str]]:
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None, None, "Coordinates must be numeric."
    if lat_f != lat_f or lon_f != lon_f:
        return None, None, "Coordinates must be finite numbers."
    if abs(lat_f) > 90 or abs(lon_f) > 180:
        return None, None, "Latitude must be between -90 and 90; longitude between -180 and 180."
    return lat_f, lon_f, None


def _throttle():
    global _LAST_CALL
    with _LOCK:
        wait = 1.05 - (time.time() - _LAST_CALL)
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL = time.time()


def _get_json(url: str):
    _throttle()
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def reverse_geocode(lat: float, lon: float, *, allow_network: bool = True) -> dict:
    lat, lon, err = validate_coords(lat, lon)
    if err:
        return {"success": False, "error": err}

    if not allow_network or not external_http_allowed():
        return {
            "success": False,
            "error": "Reverse geocoding is unavailable (network disabled or Nominatim not reachable).",
            "lat": lat,
            "lon": lon,
        }

    key = f"rev|{round(lat, 4)}|{round(lon, 4)}"
    with _LOCK:
        if key in _CACHE:
            return dict(_CACHE[key])

    params = urllib.parse.urlencode({
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        "format": "jsonv2",
        "zoom": "10",
        "addressdetails": "1",
    })
    url = f"{NOMINATIM_BASE}/reverse?{params}"
    try:
        raw = _get_json(url)
    except urllib.error.HTTPError as exc:
        return {"success": False, "error": f"Geocoder HTTP {exc.code}.", "lat": lat, "lon": lon}
    except Exception:
        return {"success": False, "error": "Reverse geocoding request failed.", "lat": lat, "lon": lon}

    if not isinstance(raw, dict) or not raw.get("address"):
        return {"success": False, "error": "No address found for these coordinates.", "lat": lat, "lon": lon}

    addr = raw["address"]
    state = addr.get("state") or addr.get("region") or ""
    district = (
        addr.get("state_district")
        or addr.get("county")
        or addr.get("district")
        or addr.get("city_district")
        or addr.get("city")
        or ""
    )
    result = {
        "success": True,
        "lat": lat,
        "lon": lon,
        "state": state,
        "district": district,
        "display_name": raw.get("display_name") or "",
        "source": "Nominatim / OpenStreetMap",
        "attribution": "© OpenStreetMap contributors",
        "error": None,
    }
    with _LOCK:
        _CACHE[key] = result
    return dict(result)


def geocode_place(query: str, *, allow_network: bool = True) -> dict:
    q = (query or "").strip()
    if len(q) < 3:
        return {"success": False, "error": "Place query is too short."}
    if not allow_network or not external_http_allowed():
        return {"success": False, "error": "Forward geocoding is unavailable."}

    key = f"fwd|{q.lower()}"
    with _LOCK:
        if key in _CACHE:
            return dict(_CACHE[key])

    params = urllib.parse.urlencode({
        "q": q,
        "format": "jsonv2",
        "limit": "1",
        "addressdetails": "1",
        "countrycodes": "in",
    })
    url = f"{NOMINATIM_BASE}/search?{params}"
    try:
        raw = _get_json(url)
    except Exception:
        return {"success": False, "error": "Forward geocoding request failed."}

    if not isinstance(raw, list) or not raw:
        return {"success": False, "error": "No coordinates found for this place."}

    hit = raw[0]
    try:
        lat = float(hit["lat"])
        lon = float(hit["lon"])
    except (KeyError, TypeError, ValueError):
        return {"success": False, "error": "Geocoder returned invalid coordinates."}

    result = {
        "success": True,
        "lat": lat,
        "lon": lon,
        "display_name": hit.get("display_name") or q,
        "source": "Nominatim / OpenStreetMap",
        "error": None,
    }
    with _LOCK:
        _CACHE[key] = result
    return dict(result)


def geocode_market(market: str, district: str, state: str, *, allow_network: bool = True) -> dict:
    parts = [p for p in [market, district, state, "India"] if p]
    return geocode_place(", ".join(parts), allow_network=allow_network)
