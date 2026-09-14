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
            # The portal publishes these and farmers price on them, so they
            # travel with the record rather than being dropped.
            "variety": row.get("Variety", "") or "",
            "grade": row.get("Grade", "") or "",
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
        # Standard contract: the frontend must key off this, never off the
        # mere presence of an API key.
        "status": "live" if live else "fallback",
        "is_live": live,
        "data_date": (records[0]["arrival_date"] if records else None),
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


# =============================================================================
# Diagnostics
# =============================================================================

def diagnose(commodity: str = "", state: str = "", district: str = "",
             market: str = "", limit: int = 200) -> dict:
    """
    Make one real call to data.gov.in and report exactly what happened.

    "Official API configured" only ever meant "the key string is not empty",
    which is why the dashboard could claim the feed was configured while every
    price shown was historical. This distinguishes the cases that were being
    conflated:

      key_missing            DATA_GOV_API_KEY (or resource id) is not set
      auth_failed            key present, the API rejected it (401/403)
      http_error             the API answered with another error status
      unreachable            no answer at all (DNS, firewall, timeout)
      bad_payload            answered, but not in the shape we expect
      no_records             authenticated, but zero rows for these filters
      no_current_record      rows returned, none dated today
      live                   rows returned and at least one is dated today

    Nothing here is cached and nothing is fabricated; the counts come from the
    response body.
    """
    out = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "api_key_present": bool(config.DATA_GOV_API_KEY),
        "resource_id_present": bool(config.DATA_GOV_RESOURCE_ID),
        "filters": {"commodity": commodity, "state": state,
                    "district": district, "market": market},
        "today": date.today().isoformat(),
    }

    if not configured():
        missing = []
        if not config.DATA_GOV_API_KEY:
            missing.append("DATA_GOV_API_KEY")
        if not config.DATA_GOV_RESOURCE_ID:
            missing.append("DATA_GOV_RESOURCE_ID")
        out.update({
            "status": "key_missing",
            "message": " and ".join(missing) + " is missing. Set it in .env "
                       "(ml/config.py loads that at import) and restart the server.",
        })
        return out

    params = {
        "api-key": config.DATA_GOV_API_KEY,
        "format": "json",
        "limit": str(max(1, min(int(limit or 200), 1000))),
        "offset": "0",
    }
    for key, value in (("commodity", commodity), ("state", state),
                       ("district", district), ("market", market)):
        if value:
            params[f"filters[{key}]"] = value

    url = f"{config.DATA_GOV_BASE_URL}/{config.DATA_GOV_RESOURCE_ID}?{urllib.parse.urlencode(params)}"
    # The key is a credential: report the URL with it redacted, never raw.
    out["request_url"] = url.replace(str(config.DATA_GOV_API_KEY), "***REDACTED***")

    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "KisanLink/1.0 (agricultural decision support)",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            out["http_status"] = resp.status
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        out["http_status"] = exc.code
        if exc.code in (401, 403):
            out.update({
                "status": "auth_failed",
                "message": ("DATA_GOV_API_KEY present but official API "
                            f"authentication failed (HTTP {exc.code}). The key "
                            "is set but rejected — check it is the data.gov.in "
                            "key for this resource and has not expired."),
            })
        else:
            out.update({
                "status": "http_error",
                "message": f"The official API answered HTTP {exc.code}.",
            })
        return out
    except Exception as exc:
        out.update({
            "status": "unreachable",
            "message": ("Could not reach data.gov.in "
                        f"({exc.__class__.__name__}). Check this machine's "
                        "network, DNS or proxy."),
        })
        return out

    # Distinguish "the response carried no records key" (a payload we do not
    # understand) from "records: []" (understood, simply empty).
    has_key = isinstance(raw, dict) and ("records" in raw or "data" in raw)
    rows = (raw.get("records") if isinstance(raw, dict) else None)
    if rows is None and isinstance(raw, dict):
        rows = raw.get("data")
    if not has_key or not isinstance(rows, list):
        out.update({"status": "bad_payload",
                    "message": ("The official API answered, but not in the shape "
                                "we expect (no 'records' list). The resource id "
                                "may point at a different dataset."),
                    "payload_keys": sorted(list(raw.keys()))[:12]
                                    if isinstance(raw, dict) else []})
        return out

    out["records_returned"] = len(rows)
    out["total_reported_by_api"] = raw.get("total")
    out["field_names"] = sorted(list(rows[0].keys()))[:20] if rows else []

    if not rows:
        out.update({
            "status": "no_records",
            "message": ("Official API reachable and authenticated, but it "
                        "returned no rows for these filters. Try removing the "
                        "district/market filter — spellings must match the "
                        "portal's own."),
        })
        return out

    # How many survive OUR normalisation, and how many are actually today's?
    today = date.today().isoformat()
    parsed, rejected, dates = 0, 0, []
    for rec in rows:
        if not isinstance(rec, dict):
            continue
        row, reason = normalize_record(rec)
        if row is None:
            rejected += 1
            continue
        parsed += 1
        d = row["Date"]
        dates.append(str(d.date()) if hasattr(d, "date") else str(d)[:10])

    out["records_parsed"] = parsed
    out["records_rejected_by_validation"] = rejected
    out["distinct_dates"] = sorted(set(dates), reverse=True)[:10]
    out["newest_date_returned"] = max(dates) if dates else None
    out["records_dated_today"] = sum(1 for d in dates if d == today)

    if out["records_dated_today"]:
        out.update({
            "status": "live",
            "message": (f"Official API returned {out['records_dated_today']} "
                        f"record(s) dated today ({today}). Live pricing is available."),
        })
    else:
        out.update({
            "status": "no_current_record",
            "message": ("Official API reachable and authenticated, but no "
                        "current record exists for this exact crop/market/filter. "
                        f"Newest row returned is dated {out['newest_date_returned']}. "
                        "AGMARKNET publishes with a lag, so this is normal early "
                        "in the day — the dashboard correctly shows LATEST "
                        "AVAILABLE rather than LIVE."),
        })
    return out
