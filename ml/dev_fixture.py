"""
KisanLink — synthetic DEVELOPMENT fixture
==========================================

This module generates a small, deterministic, **synthetic** mandi frame so the
application can be run, demonstrated, and end-to-end tested on a machine that
does not have the large historical CSVs (`ml/data/*.csv`, which are gitignored)
and does not have official `data.gov.in` credentials.

IMPORTANT — DATA HONESTY
------------------------
The rows produced here are NOT government data and NOT real mandi prices.
They are generated numbers on a realistic scale (INR per quintal) purely so
that layout, ranking, routing, and forecasting code paths can be exercised.

Nothing in this module is loaded unless the operator explicitly opts in by
setting ``KISANLINK_DEV_FIXTURE=1``. When it *is* loaded, the backend marks
every response with ``dev_fixture: true`` and a source label that says the
data is synthetic, so the UI can never present it as a live or official feed.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from . import config

#: Set this environment variable to 1/true/yes to allow the fixture to load.
ENV_FLAG = "KISANLINK_DEV_FIXTURE"

#: Shown wherever a data source would normally be named.
SOURCE_LABEL = (
    "SYNTHETIC DEVELOPMENT FIXTURE — generated sample rows, not real mandi "
    "data and not government data. Set KISANLINK_DEV_FIXTURE=0 and supply "
    "ml/data/*.csv or DATA_GOV_API_KEY for real prices."
)

#: (commodity, base modal price INR/qtl, seasonal amplitude, daily volatility)
_COMMODITIES = [
    ("Tomato", 1800.0, 420.0, 90.0),
    ("Onion", 2100.0, 500.0, 110.0),
    ("Potato", 1250.0, 240.0, 55.0),
    ("Wheat", 2350.0, 160.0, 35.0),
    ("Paddy", 2050.0, 150.0, 30.0),
    ("Soybean", 4600.0, 380.0, 95.0),
    ("Cotton", 7200.0, 520.0, 140.0),
    ("Maize", 2000.0, 180.0, 45.0),
]

#: (state, district, market, price multiplier vs the national base)
_MARKETS = [
    ("Maharashtra", "Nashik", "Pimpalgaon", 1.00),
    ("Maharashtra", "Nashik", "Lasalgaon", 0.97),
    ("Maharashtra", "Pune", "Pune Market Yard", 1.06),
    ("Maharashtra", "Solapur", "Solapur", 0.93),
    ("Karnataka", "Belagavi", "Belagavi", 0.99),
    ("Karnataka", "Bengaluru Urban", "Binny Mill", 1.08),
    ("Uttar Pradesh", "Agra", "Agra", 0.91),
    ("Uttar Pradesh", "Kanpur Nagar", "Kanpur", 0.95),
    ("Punjab", "Ludhiana", "Ludhiana", 1.02),
    ("West Bengal", "Bardhaman", "Burdwan", 0.96),
]

_VARIETIES = {
    "Tomato": ["Local", "Hybrid"],
    "Onion": ["Red", "Local"],
    "Potato": ["Jyoti", "Local"],
    "Wheat": ["Sharbati", "Dara"],
    "Paddy": ["Common", "Fine"],
    "Soybean": ["Yellow"],
    "Cotton": ["Medium Staple"],
    "Maize": ["Local", "Hybrid"],
}

_DAYS = 180


def enabled() -> bool:
    """True when the operator has explicitly opted into the synthetic fixture."""
    return os.environ.get(ENV_FLAG, "").strip().lower() in {"1", "true", "yes"}


def build_frame(days: int = _DAYS, seed: int = 20260912) -> pd.DataFrame:
    """
    Build the deterministic synthetic frame.

    Prices follow a slow seasonal curve plus bounded daily noise, so they stay
    on a believable INR/quintal scale (roughly 800–8000) and never produce the
    absurd values that broke earlier forecast displays.
    """
    rng = np.random.default_rng(seed)
    end = pd.Timestamp.today().normalize()
    dates = pd.date_range(end=end, periods=days, freq="D")
    day_index = np.arange(days)

    rows = []
    for commodity, base, amplitude, volatility in _COMMODITIES:
        varieties = _VARIETIES.get(commodity, ["Local"])
        season = amplitude * np.sin(2 * np.pi * day_index / 120.0)
        for state, district, market, multiplier in _MARKETS:
            # Deterministic per-series walk, bounded so it cannot drift absurdly.
            noise = rng.normal(0.0, volatility, days).cumsum() * 0.25
            noise = np.clip(noise, -3 * volatility, 3 * volatility)
            modal = (base + season + noise) * multiplier
            modal = np.clip(modal, base * 0.45, base * 1.85)

            spread = np.clip(rng.normal(0.09, 0.02, days), 0.03, 0.18)
            min_price = modal * (1.0 - spread)
            max_price = modal * (1.0 + spread)
            variety = varieties[hash((commodity, market)) % len(varieties)]

            for i, day in enumerate(dates):
                # Mandis do not trade every single day.
                if (i + hash(market)) % 7 == 6:
                    continue
                rows.append({
                    config.COL_STATE: state,
                    config.COL_DISTRICT: district,
                    config.COL_MARKET: market,
                    config.COL_COMMODITY: commodity,
                    config.COL_VARIETY: variety,
                    config.COL_GRADE: "FAQ",
                    config.COL_DATE: day,
                    config.COL_MIN_PRICE: round(float(min_price[i]), 2),
                    config.COL_MAX_PRICE: round(float(max_price[i]), 2),
                    config.COL_MODAL_PRICE: round(float(modal[i]), 2),
                })

    frame = pd.DataFrame(rows)
    from .data_loader import _add_filter_columns
    return _add_filter_columns(frame)
