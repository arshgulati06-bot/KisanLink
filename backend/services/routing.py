"""
Road routing: OpenRouteService (if ROUTING_API_KEY) then public OSRM, else Haversine.

Haversine is never labelled as a road distance. estimated=true in that case.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from ml.transport import haversine_km
from services.geocode import external_http_allowed, validate_coords

ORS_BASE = os.environ.get(
    "ORS_BASE_URL", "https://api.openrouteservice.org"
).rstrip("/")
OSRM_BASE = os.environ.get(
    "OSRM_BASE_URL", "https://router.project-osrm.org"
).rstrip("/")

_CACHE = {}
_LOCK = threading.Lock()


def routing_api_key() -> str:
    return (
        os.environ.get("ROUTING_API_KEY", "").strip()
        or os.environ.get("ORS_API_KEY", "").strip()
    )


def _cache_get(key):
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit["ts"] < 3600:
            return dict(hit["data"])
    return None


def _cache_set(key, data):
    with _LOCK:
        _CACHE[key] = {"ts": time.time(), "data": data}


def compute_route(origin_lat, origin_lon, dest_lat, dest_lon, *, allow_network: bool = True) -> dict:
    o_lat, o_lon, err = validate_coords(origin_lat, origin_lon)
    if err:
        return {"success": False, "error": f"Invalid origin: {err}", "estimated": True}
    d_lat, d_lon, err = validate_coords(dest_lat, dest_lon)
    if err:
        return {"success": False, "error": f"Invalid destination: {err}", "estimated": True}

    key = f"{round(o_lat, 4)}|{round(o_lon, 4)}|{round(d_lat, 4)}|{round(d_lon, 4)}"
    cached = _cache_get(key)
    if cached:
        cached["cached"] = True
        return cached

    if allow_network and external_http_allowed():
        key_ors = routing_api_key()
        if key_ors:
            routed = _openroute(o_lat, o_lon, d_lat, d_lon, key_ors)
            if routed.get("success"):
                _cache_set(key, routed)
                return routed
        osrm = _osrm(o_lat, o_lon, d_lat, d_lon)
        if osrm.get("success"):
            _cache_set(key, osrm)
            return osrm

    km = max(0.1, haversine_km(o_lat, o_lon, d_lat, d_lon))
    fallback = {
        "success": True,
        "distance_km": round(km, 1),
        "duration_minutes": None,
        "source": "haversine",
        "estimated": True,
        "error": None,
        "note": "Road routing unavailable — straight-line distance estimate.",
    }
    _cache_set(key, fallback)
    return fallback


def _openroute(o_lat, o_lon, d_lat, d_lon, api_key: str) -> dict:
    params = urllib.parse.urlencode({
        "api_key": api_key,
        "start": f"{o_lon},{o_lat}",
        "end": f"{d_lon},{d_lat}",
    })
    url = f"{ORS_BASE}/v2/directions/driving-car?{params}"
    try:
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json, application/geo+json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {"success": False, "estimated": True, "error": "OpenRouteService request failed."}

    try:
        feat = (raw.get("features") or [None])[0]
        props = feat.get("properties") or {}
        summary = props.get("summary") or {}
        meters = float(summary.get("distance"))
        seconds = float(summary.get("duration"))
    except Exception:
        return {"success": False, "estimated": True, "error": "OpenRouteService payload unexpected."}

    return {
        "success": True,
        "distance_km": round(meters / 1000.0, 1),
        "duration_minutes": round(seconds / 60.0, 1),
        "source": "openrouteservice",
        "estimated": False,
        "error": None,
    }


def _osrm(o_lat, o_lon, d_lat, d_lon) -> dict:
    url = (
        f"{OSRM_BASE}/route/v1/driving/"
        f"{o_lon},{o_lat};{d_lon},{d_lat}?overview=false"
    )
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"success": False, "estimated": True, "error": f"OSRM HTTP {exc.code}."}
    except Exception:
        return {"success": False, "estimated": True, "error": "OSRM request failed."}

    routes = raw.get("routes") or []
    if raw.get("code") != "Ok" or not routes:
        return {"success": False, "estimated": True, "error": "OSRM returned no route."}
    meters = float(routes[0].get("distance") or 0)
    seconds = float(routes[0].get("duration") or 0)
    return {
        "success": True,
        "distance_km": round(meters / 1000.0, 1),
        "duration_minutes": round(seconds / 60.0, 1),
        "source": "osrm",
        "estimated": False,
        "error": None,
        "note": "Public OSRM instance — no production SLA. Set ROUTING_API_KEY for OpenRouteService.",
    }
