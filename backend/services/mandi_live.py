"""
Official data.gov.in / AGMARKNET mandi adapter.

Does not invent prices. Does not claim LIVE unless a successful fetch
returns records and credentials are configured.

Requires:
  DATA_GOV_API_KEY
  DATA_GOV_RESOURCE_ID
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Optional

from ml import config
from ml.ingest import normalize_record, official_api_configured

_CACHE = {}
_LOCK = threading.Lock()
CACHE_SECONDS = int(os.environ.get("KISANLINK_MANDI_CACHE_SECONDS", "600") or "600")


def configured() -> bool:
    return official_api_configured()


def _cache_key(commodity, state, district, market, limit) -> str:
    return "|".join([
        (commodity or "").lower(),
        (state or "").lower(),
        (district or "").lower(),
        (market or "").lower(),
        str(limit),
    ])


def fetch_live_prices(
    commodity: str = "",
    state: str = "",
    district: str = "",
    market: str = "",
    limit: int = 200,
) -> dict:
    """
    Fetch current mandi rows from data.gov.in.

    Returns success=False when credentials are missing or the API fails.
    Never fills prices from random/demo values.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    if not configured():
        return {
            "success": False,
            "configured": False,
            "live": False,
            "records": [],
            "fetched_at": fetched_at,
            "source": "data.gov.in",
            "error": (
                "Live government mandi feed cannot be activated until "
                "DATA_GOV_API_KEY and DATA_GOV_RESOURCE_ID are configured."
            ),
        }

    limit = max(1, min(int(limit or 200), 500))
    key = _cache_key(commodity, state, district, market, limit)
    now = time.time()
    today_iso = date.today().isoformat()
    with _LOCK:
        hit = _CACHE.get(key)
        # A cached payload carries a frozen "is this today?" verdict, so an
        # entry built at 23:58 would still claim TODAY'S LIVE MANDI DATA a few
        # minutes after midnight. Expire on the date as well as the TTL.
        if (hit and now - hit["ts"] < CACHE_SECONDS
                and hit.get("day") == today_iso):
            payload = dict(hit["data"])
            payload["cached"] = True
            return payload

    params = {
        "api-key": config.DATA_GOV_API_KEY,
        "format": "json",
        "limit": str(limit),
        "offset": "0",
    }
    if commodity:
        params["filters[commodity]"] = commodity
    if state:
        params["filters[state]"] = state
    if district:
        params["filters[district]"] = district
    if market:
        params["filters[market]"] = market

    url = f"{config.DATA_GOV_BASE_URL}/{config.DATA_GOV_RESOURCE_ID}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "KisanLink/1.0 (agricultural decision support)",
            },
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return _fail(fetched_at, f"Official mandi API HTTP {exc.code}.", configured=True)
    except Exception:
        return _fail(fetched_at, "Official mandi API request failed or timed out.", configured=True)

    rows = raw.get("records") or raw.get("data") or []
    if not isinstance(rows, list):
        return _fail(fetched_at, "Official mandi API returned an unexpected payload.", configured=True)

    today = today_iso
    records = []
    for rec in rows:
        if not isinstance(rec, dict):
            continue
        row, _reason = normalize_record(rec)
        if row is None:
            continue
        arrival = str(row["Date"].date()) if hasattr(row["Date"], "date") else str(row["Date"])[:10]
        records.append({
            "commodity": row.get("Commodity", ""),
            "state": row.get("State", ""),
            "district": row.get("District", ""),
            "market": row.get("Market", ""),
            "arrival_date": arrival,
            "min_price": _opt_float(row.get("Min_Price")),
            "max_price": _opt_float(row.get("Max_Price")),
            "modal_price": float(row["Modal_Price"]),
            "unit": "INR per quintal",
            "is_today": arrival == today,
            "source": "data.gov.in / AGMARKNET",
        })

    # Newest arrival first, so the UI's "latest_date" and first row reflect
    # today's record when the official feed has published one.
    records.sort(key=lambda r: (r["is_today"], r["arrival_date"]), reverse=True)
    live = bool(records) and any(r["is_today"] for r in records)
    result = {
        "success": True,
        "configured": True,
        "live": live,
        "records": records,
        "count": len(records),
        "fetched_at": fetched_at,
        "cached": False,
        "source": "data.gov.in / AGMARKNET",
        "label": "TODAY'S LIVE MANDI DATA" if live else "LATEST AVAILABLE MANDI DATA",
        "error": None,
        "note": (
            "Records from a successful official API response."
            if records else
            "Official API responded but no matching rows after validation."
        ),
    }
    with _LOCK:
        _CACHE[key] = {"ts": now, "day": today_iso, "data": result}
    return result


def _opt_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        v = float(value)
        if v != v or v in (float("inf"), float("-inf")):
            return None
        return round(v, 2)
    except (TypeError, ValueError):
        return None


def _fail(fetched_at: str, error: str, configured: bool) -> dict:
    return {
        "success": False,
        "configured": configured,
        "live": False,
        "records": [],
        "fetched_at": fetched_at,
        "source": "data.gov.in",
        "error": error,
    }
