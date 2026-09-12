"""
Validate Chronos outputs against the selected market's recent history.

Does not invent mandi prices. When the model path leaves a plausible
band around the latest real observations, the displayed point forecast
falls back to the last validated modal price and uncertainty is flagged.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


SANITY_LOW_MULT = 0.20
SANITY_HIGH_MULT = 5.00


def recent_anchor(prices) -> dict:
    arr = np.asarray(prices, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return {"anchor": None, "low": None, "high": None, "last": None}
    window = arr[-min(len(arr), 30):]
    anchor = float(np.median(window))
    last = float(arr[-1])
    q1, q3 = np.percentile(window, 25), np.percentile(window, 75)
    iqr = float(max(q3 - q1, anchor * 0.05))
    low = max(1.0, min(anchor * SANITY_LOW_MULT, last * SANITY_LOW_MULT))
    high = max(anchor * SANITY_HIGH_MULT, last * SANITY_HIGH_MULT, anchor + 8 * iqr)
    return {"anchor": anchor, "low": low, "high": high, "last": last}


def drop_inconsistent_scale(prices, dates, min_keep: int):
    """Drop days whose price is wildly off the series median (mixed units)."""
    prices = np.asarray(prices, dtype=float)
    if len(prices) < 4:
        return prices, dates, 0
    med = float(np.median(prices[prices > 0])) if np.any(prices > 0) else 0.0
    if med <= 0:
        return prices, dates, 0
    mask = (prices >= med / 15.0) & (prices <= med * 15.0) & np.isfinite(prices)
    if int(mask.sum()) >= min_keep:
        dropped = int((~mask).sum())
        if dropped:
            date_index = pd.DatetimeIndex(dates)
            return prices[mask], date_index[mask], dropped
    return prices, dates, 0


def sanitize_forecast(low, median, high, recent_prices) -> dict:
    """
    Keep Chronos quantiles when they sit on the same scale as recent
    modal prices. Otherwise replace the displayed path with the last
    real observation (not a fabricated mandi quote).
    """
    low = np.asarray(low, dtype=float).copy()
    median = np.asarray(median, dtype=float).copy()
    high = np.asarray(high, dtype=float).copy()
    stats = recent_anchor(recent_prices)
    notes = []
    applied = False

    for arr in (low, median, high):
        arr[~np.isfinite(arr)] = np.nan
        np.maximum(arr, 0.0, out=arr)

    if stats["anchor"] is None:
        notes.append("No positive historical prices available to validate the forecast scale.")
        return {
            "low": np.nan_to_num(low, nan=0.0),
            "median": np.nan_to_num(median, nan=0.0),
            "high": np.nan_to_num(high, nan=0.0),
            "applied": True,
            "notes": notes,
            "anchor": None,
        }

    last = stats["last"]
    lo_b, hi_b = stats["low"], stats["high"]
    med_mid = float(np.nanmedian(median)) if np.isfinite(median).any() else last
    ratio = med_mid / last if last else 0.0
    exploded = (not np.isfinite(med_mid)) or ratio > SANITY_HIGH_MULT or ratio < SANITY_LOW_MULT

    if exploded:
        applied = True
        median[:] = last
        low[:] = max(1.0, last * 0.92)
        high[:] = last * 1.08
        notes.append(
            f"Chronos output (median ≈ ₹{med_mid:,.0f}/QTL) was outside the "
            f"validated recent scale (last modal ₹{last:,.0f}/QTL). "
            "The displayed forecast uses the last validated mandi price; "
            "treat direction as uncertain."
        )
    else:
        raw_med = median.copy()
        median = np.clip(median, lo_b, hi_b)
        low = np.clip(np.minimum(low, median), lo_b, hi_b)
        high = np.clip(np.maximum(high, median), lo_b, hi_b)
        if not np.allclose(raw_med, median, rtol=0.02, atol=1.0):
            applied = True
            notes.append(
                "One or more forecast days were clipped to a band around recent "
                "mandi observations so an out-of-scale model path is not shown as the price."
            )

    low = np.minimum(low, median)
    high = np.maximum(high, median)
    return {
        "low": low,
        "median": median,
        "high": high,
        "applied": applied,
        "notes": notes,
        "anchor": stats["anchor"],
        "last": last,
        "band": {"low": lo_b, "high": hi_b},
    }
