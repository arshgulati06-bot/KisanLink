"""
KisanLink — Mandi record ingestion
===================================
Normalize, validate, deduplicate, persist, and log new mandi rows.

Does not invent prices. Does not call an official API unless
DATA_GOV_API_KEY and DATA_GOV_RESOURCE_ID are set in the environment.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import pandas as pd

from . import config

_APMC_RE = re.compile(r"\s+APMC\s*$", re.IGNORECASE)
_PATH_RE = re.compile(r"([a-zA-Z]:[\\/]|[\\/]{2,}|\.\./)")

_COLUMN_ALIASES = {
    "state": config.COL_STATE,
    "STATE": config.COL_STATE,
    "District Name": config.COL_DISTRICT,
    "district_name": config.COL_DISTRICT,
    "district": config.COL_DISTRICT,
    "Market Name": config.COL_MARKET,
    "market_name": config.COL_MARKET,
    "market": config.COL_MARKET,
    "commodity": config.COL_COMMODITY,
    "variety": config.COL_VARIETY,
    "grade": config.COL_GRADE,
    "Arrival_Date": config.COL_DATE,
    "arrival_date": config.COL_DATE,
    "Price Date": config.COL_DATE,
    "price_date": config.COL_DATE,
    "date": config.COL_DATE,
    "Min_Price": config.COL_MIN_PRICE,
    "min_price": config.COL_MIN_PRICE,
    "Max_Price": config.COL_MAX_PRICE,
    "max_price": config.COL_MAX_PRICE,
    "Modal_Price": config.COL_MODAL_PRICE,
    "modal_price": config.COL_MODAL_PRICE,
    "modalprice": config.COL_MODAL_PRICE,
}

_CANONICAL = [
    config.COL_STATE, config.COL_DISTRICT, config.COL_MARKET,
    config.COL_COMMODITY, config.COL_VARIETY, config.COL_GRADE,
    config.COL_DATE, config.COL_MIN_PRICE, config.COL_MAX_PRICE,
    config.COL_MODAL_PRICE,
]

logger = logging.getLogger("kisanlink.ingest")


def _ensure_log():
    os.makedirs(config.INGEST_DIR, exist_ok=True)
    if not logger.handlers:
        handler = logging.FileHandler(config.INGEST_LOG_PATH, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def canonical_column(name: str) -> str:
    key = str(name).strip()
    if key in _COLUMN_ALIASES:
        return _COLUMN_ALIASES[key]
    if key in {c for c in _CANONICAL}:
        return key
    lowered = key.lower().replace(" ", "_")
    return _COLUMN_ALIASES.get(lowered, key)


def normalize_place_name(value: Any, strip_apmc: bool = False) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return ""
    if strip_apmc:
        text = _APMC_RE.sub("", text).strip()
    return text.title()


def parse_date(value: Any) -> Optional[pd.Timestamp]:
    if value is None or value == "":
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        ts = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts).normalize()


def parse_price(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        price = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if not (config.MIN_MODAL_PRICE <= price <= config.MAX_MODAL_PRICE):
        return None
    return price


def _looks_like_path(value: str) -> bool:
    return bool(_PATH_RE.search(value))


def normalize_record(raw: dict) -> tuple[Optional[dict], Optional[str]]:
    """Return (canonical_row, reject_reason)."""
    if not isinstance(raw, dict):
        return None, "record_not_object"
    normalized = {}
    for key, val in raw.items():
        if key in ("_source", "_ingested_at", "source"):
            continue
        col = canonical_column(str(key))
        if col in _CANONICAL:
            normalized[col] = val

    for field in (config.COL_STATE, config.COL_DISTRICT, config.COL_COMMODITY):
        name = normalize_place_name(normalized.get(field), strip_apmc=False)
        if not name:
            return None, f"missing_{field.lower()}"
        if _looks_like_path(name):
            return None, "path_not_allowed"
        normalized[field] = name

    market = normalize_place_name(normalized.get(config.COL_MARKET), strip_apmc=True)
    if not market:
        return None, "missing_market"
    if _looks_like_path(market):
        return None, "path_not_allowed"
    normalized[config.COL_MARKET] = market

    dt = parse_date(normalized.get(config.COL_DATE))
    if dt is None:
        return None, "invalid_date"
    normalized[config.COL_DATE] = dt

    price = parse_price(normalized.get(config.COL_MODAL_PRICE))
    if price is None:
        return None, "invalid_modal_price"
    normalized[config.COL_MODAL_PRICE] = price

    for pcol in (config.COL_MIN_PRICE, config.COL_MAX_PRICE):
        if pcol in normalized and normalized[pcol] not in (None, ""):
            parsed = parse_price(normalized[pcol])
            if parsed is None:
                return None, f"invalid_{pcol.lower()}"
            normalized[pcol] = parsed
        else:
            normalized[pcol] = pd.NA

    min_price = normalized[config.COL_MIN_PRICE]
    max_price = normalized[config.COL_MAX_PRICE]
    if pd.notna(min_price) and pd.notna(max_price):
        if min_price > max_price or not (min_price <= price <= max_price):
            return None, "price_range_inconsistent"

    for extra in (config.COL_VARIETY, config.COL_GRADE):
        val = normalized.get(extra)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            normalized[extra] = ""
        else:
            normalized[extra] = str(val).strip()

    return normalized, None


def record_key(row: dict) -> str:
    date_val = row[config.COL_DATE]
    date_s = str(pd.Timestamp(date_val).date())
    return "|".join([
        str(row[config.COL_STATE]).lower(),
        str(row[config.COL_DISTRICT]).lower(),
        str(row[config.COL_MARKET]).lower(),
        str(row[config.COL_COMMODITY]).lower(),
        date_s,
        str(row.get(config.COL_VARIETY, "")).lower(),
        str(row.get(config.COL_GRADE, "")).lower(),
    ])


def keys_from_frame(df: pd.DataFrame) -> set:
    if df is None or df.empty:
        return set()
    dates = pd.to_datetime(df[config.COL_DATE]).dt.strftime("%Y-%m-%d")
    variety = df[config.COL_VARIETY].fillna("").astype(str).str.lower() if config.COL_VARIETY in df.columns else ""
    grade = df[config.COL_GRADE].fillna("").astype(str).str.lower() if config.COL_GRADE in df.columns else ""
    return set(
        df[config.COL_STATE].astype(str).str.lower()
        + "|" + df[config.COL_DISTRICT].astype(str).str.lower()
        + "|" + df[config.COL_MARKET].astype(str).str.lower()
        + "|" + df[config.COL_COMMODITY].astype(str).str.lower()
        + "|" + dates
        + "|" + variety
        + "|" + grade
    )


def load_ingested_frame() -> pd.DataFrame:
    path = config.INGESTED_RECORDS_PATH
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame(columns=_CANONICAL)
    df = pd.read_csv(path, parse_dates=[config.COL_DATE], low_memory=False)
    return df


def persist_new_rows(rows: list[dict]) -> None:
    if not rows:
        return
    os.makedirs(config.INGEST_DIR, exist_ok=True)
    append_df = pd.DataFrame(rows)[_CANONICAL]
    header = not os.path.exists(config.INGESTED_RECORDS_PATH)
    append_df.to_csv(config.INGESTED_RECORDS_PATH, mode="a", header=header, index=False)


def ingest_records(
    records: Iterable[dict],
    existing_df: pd.DataFrame,
    source: str = "json_post",
    persist: bool = True,
) -> dict:
    """
    Validate and append records. Safe to run repeatedly.

    Returns inserted / skipped / rejected counts and latest dataset date.
    """
    _ensure_log()
    records = list(records or [])
    rejected = 0
    reject_reasons: dict[str, int] = {}
    valid_rows = []

    if len(records) > config.INGEST_MAX_RECORDS:
        logger.warning("Rejected payload: %s records exceeds max %s", len(records), config.INGEST_MAX_RECORDS)
        return {
            "success": False,
            "error": f"Too many records (max {config.INGEST_MAX_RECORDS}).",
            "inserted": 0,
            "added": 0,
            "skipped": 0,
            "duplicates_skipped": 0,
            "rejected": len(records),
            "invalid_skipped": len(records),
            "new_total": len(existing_df),
            "latest_date_in_dataset": _latest_date(existing_df),
        }

    for rec in records:
        row, reason = normalize_record(rec)
        if row is None:
            rejected += 1
            reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
            logger.info("Rejected record (%s): %s", reason, _safe_preview(rec))
            continue
        valid_rows.append(row)

    existing_keys = keys_from_frame(existing_df)
    added_rows = []
    duplicates = 0
    for row in valid_rows:
        key = record_key(row)
        if key in existing_keys:
            duplicates += 1
            continue
        existing_keys.add(key)
        added_rows.append(row)

    new_df = existing_df
    if added_rows:
        add_frame = pd.DataFrame(added_rows)
        helper_cols = [c for c in existing_df.columns if str(c).startswith("_")]
        base = existing_df.drop(columns=helper_cols, errors="ignore")
        new_df = pd.concat([base, add_frame[_CANONICAL]], ignore_index=True)
        new_df = new_df.sort_values(config.COL_DATE).reset_index(drop=True)
        from .data_loader import _add_filter_columns
        new_df = _add_filter_columns(new_df)
        if persist:
            persist_new_rows(added_rows)
            try:
                from .data_loader import invalidate_combined_cache
                invalidate_combined_cache()
            except Exception:
                pass
        logger.info(
            "Ingested %s rows from %s (dup=%s rejected=%s)",
            len(added_rows), source, duplicates, rejected,
        )

    return {
        "success": True,
        "inserted": len(added_rows),
        "added": len(added_rows),
        "skipped": duplicates,
        "duplicates_skipped": duplicates,
        "rejected": rejected,
        "invalid_skipped": rejected,
        "reject_reasons": reject_reasons,
        "new_total": len(new_df),
        "latest_date_in_dataset": _latest_date(new_df),
        "frame": new_df,
        "source": source,
    }


def _latest_date(df: pd.DataFrame) -> Optional[str]:
    if df is None or df.empty or config.COL_DATE not in df.columns:
        return None
    return str(pd.to_datetime(df[config.COL_DATE]).max().date())


def _safe_preview(rec: Any) -> str:
    try:
        text = json.dumps(rec, default=str)[:300]
    except TypeError:
        text = str(rec)[:300]
    return text.replace("\\", "_")


def official_api_configured() -> bool:
    return bool(config.DATA_GOV_API_KEY and config.DATA_GOV_RESOURCE_ID)


def fetch_official_records(limit: int = 1000, offset: int = 0) -> dict:
    """
    Pull records from data.gov.in only when API key + resource id exist.
    Never fabricates a successful live fetch.
    """
    _ensure_log()
    if not official_api_configured():
        return {
            "success": False,
            "configured": False,
            "records": [],
            "error": (
                "Official mandi API is not configured. Set DATA_GOV_API_KEY and "
                "DATA_GOV_RESOURCE_ID in the environment."
            ),
        }

    import urllib.parse
    import urllib.request

    params = urllib.parse.urlencode({
        "api-key": config.DATA_GOV_API_KEY,
        "format": "json",
        "limit": max(1, min(int(limit), config.INGEST_MAX_RECORDS)),
        "offset": max(0, int(offset)),
    })
    url = f"{config.DATA_GOV_BASE_URL}/{config.DATA_GOV_RESOURCE_ID}?{params}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Official API fetch failed: %s", type(exc).__name__)
        return {
            "success": False,
            "configured": True,
            "records": [],
            "error": "Official API request failed.",
        }

    records = payload.get("records") or payload.get("data") or []
    if not isinstance(records, list):
        return {
            "success": False,
            "configured": True,
            "records": [],
            "error": "Official API returned an unexpected payload.",
        }
    return {"success": True, "configured": True, "records": records, "error": None}


def load_buyer_demands() -> tuple[list, str]:
    """Load project buyer requirements. Returns (demands, provenance_note)."""
    path = config.BUYER_DEMANDS_PATH
    if not os.path.exists(path):
        return [], "No buyer-demand file is present."
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    demands = data.get("demands") if isinstance(data, dict) else data
    if not isinstance(demands, list):
        return [], "Buyer-demand file is invalid."
    note = data.get("note") if isinstance(data, dict) else (
        "Buyer requirements loaded from project data file."
    )
    return demands, note or "Buyer requirements loaded from project data file."
