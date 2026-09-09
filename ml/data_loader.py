"""
KisanLink ML Pipeline — Data Loading & Cleaning
=================================================
Functions for loading, normalizing, combining, filtering and preparing
the mandi price dataset for Chronos forecasting.

Three source datasets are combined into one common schema:

  Agriculture_price_dataset.csv  — columns: STATE, District Name, Market Name,
                                             Commodity, Variety, Grade,
                                             Price Date, Min_Price, Max_Price,
                                             Modal_Price
  2022.csv / 2026.csv            — columns: State, District, Market,
                                             Commodity, Variety, Grade,
                                             Arrival_Date, Min_Price, Max_Price,
                                             Modal_Price, Commodity_Code

Normalized canonical schema (config.COL_*):
  State, District, Market, Commodity, Variety, Grade,
  Date, Min_Price, Max_Price, Modal_Price

Market name normalization:
  The 2026 dataset appends " APMC" to many market names (e.g. "Pimpalgaon APMC")
  that appear without the suffix in earlier datasets (e.g. "Pimpalgaon").
  This is the same physical market with a different naming convention.
  We strip the " APMC" suffix during normalization so all three datasets
  refer to the same market by the same name.

  The stripping is applied ONLY during loading/normalization, not during
  user input matching — so a user can still type "Pimpalgaon APMC" and the
  existing fuzzy resolver will match it to "Pimpalgaon" in the combined data.
"""

import re
import os

import pandas as pd
import torch
import numpy as np

from . import config


# =============================================================================
# Internal helpers
# =============================================================================

# Regex to strip " APMC" suffix (case-insensitive, tolerates trailing spaces)
_APMC_RE = re.compile(r"\s+APMC\s*$", re.IGNORECASE)


def _strip_apmc(series: pd.Series) -> pd.Series:
    """Remove trailing ' APMC' (case-insensitive) from a string Series."""
    return series.str.replace(_APMC_RE, "", regex=True)


def _normalize_strings(df: pd.DataFrame) -> pd.DataFrame:
    """
    In-place normalization of string columns in a DataFrame that already
    uses the canonical column names (State, District, Market, Commodity,
    Variety, Grade, Date, Min_Price, Max_Price, Modal_Price).

    Steps:
    1. Strip leading/trailing whitespace from all string columns.
    2. Strip ' APMC' suffix from Market names.
    3. Apply .str.title() to State, District, Market, Commodity
       so case variations (e.g. 'nashik' → 'Nashik') are unified.
    4. Parse 'Date' column to datetime (handles ISO and M/D/YYYY formats).
    5. Convert price columns to numeric (coerce errors to NaN).
    6. Drop rows where Date or Modal_Price is NaN.
    7. Remove exact duplicate rows.
    """
    # --- Strip whitespace from string columns ---
    str_cols = [
        config.COL_STATE, config.COL_DISTRICT, config.COL_MARKET,
        config.COL_COMMODITY, config.COL_VARIETY, config.COL_GRADE,
    ]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # --- Strip APMC suffix from Market before title-casing ---
    if config.COL_MARKET in df.columns:
        df[config.COL_MARKET] = _strip_apmc(df[config.COL_MARKET])

    # --- Title-case the key geographic/commodity fields for consistency ---
    for col in [config.COL_STATE, config.COL_DISTRICT,
                config.COL_MARKET, config.COL_COMMODITY]:
        if col in df.columns:
            df[col] = df[col].str.title()

    # --- Parse Date ---
    df[config.COL_DATE] = pd.to_datetime(
        df[config.COL_DATE],
        errors="coerce",
        dayfirst=False,
    )

    # --- Convert price columns to numeric ---
    for price_col in [config.COL_MIN_PRICE,
                      config.COL_MAX_PRICE,
                      config.COL_MODAL_PRICE]:
        if price_col in df.columns:
            df[price_col] = pd.to_numeric(df[price_col], errors="coerce")

    # --- Drop rows with missing critical fields ---
    df = df.dropna(subset=[config.COL_DATE, config.COL_MODAL_PRICE])

    return df


def _load_agriculture(path: str) -> pd.DataFrame:
    """
    Load the Agriculture_price_dataset.csv and rename its columns to the
    canonical schema.  Drops columns not in the canonical schema.
    """
    df = pd.read_csv(path, low_memory=False)
    df.columns = df.columns.str.strip()

    df = df.rename(columns={
        "STATE":        config.COL_STATE,
        "District Name": config.COL_DISTRICT,
        "Market Name":  config.COL_MARKET,
        "Price Date":   config.COL_DATE,
    })

    # Keep only canonical columns that exist
    keep = [c for c in [
        config.COL_STATE, config.COL_DISTRICT, config.COL_MARKET,
        config.COL_COMMODITY, config.COL_VARIETY, config.COL_GRADE,
        config.COL_DATE, config.COL_MIN_PRICE,
        config.COL_MAX_PRICE, config.COL_MODAL_PRICE,
    ] if c in df.columns]

    return df[keep]


def _load_arrival(path: str) -> pd.DataFrame:
    """
    Load a 2022.csv or 2026.csv (Arrival_Date schema) and rename its
    columns to the canonical schema.  Drops Commodity_Code.
    """
    df = pd.read_csv(path, low_memory=False)
    df.columns = df.columns.str.strip()

    df = df.rename(columns={
        "Arrival_Date": config.COL_DATE,
    })

    # Keep only canonical columns that exist
    keep = [c for c in [
        config.COL_STATE, config.COL_DISTRICT, config.COL_MARKET,
        config.COL_COMMODITY, config.COL_VARIETY, config.COL_GRADE,
        config.COL_DATE, config.COL_MIN_PRICE,
        config.COL_MAX_PRICE, config.COL_MODAL_PRICE,
    ] if c in df.columns]

    return df[keep]


# =============================================================================
# load_combined_data  (primary public entry point)
# =============================================================================

def load_combined_data() -> pd.DataFrame:
    """
    Load, normalize, and combine all three mandi price CSV datasets into
    a single clean DataFrame using the canonical column schema.

    Data sources (in ml/data/):
      - Agriculture_price_dataset.csv  (Jun 2023 – Jun 2025)
      - 2022.csv                       (Jan – Dec 2022)
      - 2026.csv                       (Dec 2025 – Apr 2026)

    Normalization applied to each source:
      • Column renames to canonical schema
      • Whitespace stripping on all string columns
      • ' APMC' suffix stripped from Market names
      • Title-casing of State, District, Market, Commodity
      • Date parsing (handles both ISO yyyy-mm-dd and M/D/YYYY)
      • Price columns coerced to float
      • Rows with invalid Date or missing Modal_Price dropped
      • Exact duplicate rows removed after combining
      • Result sorted chronologically by Date

    Returns
    -------
    pd.DataFrame
        Combined and cleaned DataFrame with canonical column names.

    Raises
    ------
    FileNotFoundError
        If any of the three CSV files are missing.
    """
    sources = [
        (config.CSV_AGRICULTURE, _load_agriculture),
        (config.CSV_2022,        _load_arrival),
        (config.CSV_2026,        _load_arrival),
    ]

    frames = []
    for path, loader_fn in sources:
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Dataset not found: {path}\n"
                "Ensure all three CSV files are present in ml/data/"
            )
        df = loader_fn(path)
        df = _normalize_strings(df)
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)

    # Remove exact duplicates (same row across datasets)
    combined = combined.drop_duplicates()

    # Sort chronologically
    combined = combined.sort_values(config.COL_DATE).reset_index(drop=True)

    return combined


# =============================================================================
# load_data  (kept for --csv CLI override / backward compatibility)
# =============================================================================

def load_data(csv_path=None) -> pd.DataFrame:
    """
    Load a single mandi price CSV into a DataFrame.

    When csv_path is None, delegates to load_combined_data() which loads
    and normalizes all three datasets.

    When csv_path is explicitly given (e.g. via the --csv CLI flag), loads
    only that file and auto-detects the schema (Agriculture or Arrival_Date).

    Parameters
    ----------
    csv_path : str, optional
        Path to a specific CSV file.  Defaults to load_combined_data().

    Returns
    -------
    pd.DataFrame
        Raw DataFrame with whitespace-stripped column names.
        (Call clean_data() after this when using a single-file path.)
    """
    if csv_path is None:
        return load_combined_data()

    df = pd.read_csv(csv_path, low_memory=False)
    df.columns = df.columns.str.strip()
    return df


# =============================================================================
# clean_data  (kept for single-file --csv override path)
# =============================================================================

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate and clean a raw mandi price DataFrame loaded from a single CSV.

    Used only when a custom --csv path is supplied to the CLI.
    The combined loader (load_combined_data) already performs all of these
    steps internally, so this function is a no-op for combined data.

    Steps:
    1. Auto-detect and rename columns to canonical schema if needed.
    2. Strip whitespace; strip APMC suffix; title-case key fields.
    3. Parse Date, coerce prices, drop invalid rows.
    4. Remove exact duplicates.
    5. Sort chronologically.

    Parameters
    ----------
    df : pd.DataFrame
        Raw DataFrame from load_data(csv_path).

    Returns
    -------
    pd.DataFrame
        Cleaned DataFrame with canonical column names.
    """
    df = df.copy()

    # --- Auto-detect and rename to canonical schema ---
    if "STATE" in df.columns:
        # Agriculture schema
        df = df.rename(columns={
            "STATE":         config.COL_STATE,
            "District Name": config.COL_DISTRICT,
            "Market Name":   config.COL_MARKET,
            "Price Date":    config.COL_DATE,
        })
    elif "Arrival_Date" in df.columns:
        # 2022 / 2026 schema
        df = df.rename(columns={"Arrival_Date": config.COL_DATE})

    # Keep only canonical columns
    keep = [c for c in [
        config.COL_STATE, config.COL_DISTRICT, config.COL_MARKET,
        config.COL_COMMODITY, config.COL_VARIETY, config.COL_GRADE,
        config.COL_DATE, config.COL_MIN_PRICE,
        config.COL_MAX_PRICE, config.COL_MODAL_PRICE,
    ] if c in df.columns]
    df = df[keep]

    # --- Normalize ---
    df = _normalize_strings(df)

    # --- Remove exact duplicates ---
    df = df.drop_duplicates()

    # --- Sort chronologically ---
    df = df.sort_values(config.COL_DATE).reset_index(drop=True)

    return df


# =============================================================================
# get_market_data
# =============================================================================

def get_market_data(df, commodity, state, district, market):
    """
    Filter the combined dataset for a specific market.

    Matching is case-insensitive.  The stored data has already been
    title-cased and APMC-stripped, so if a user passes "Pimpalgaon APMC"
    it becomes "Pimpalgaon" after stripping, and will match the stored
    "Pimpalgaon" rows correctly.

    If no exact match is found, attempts to resolve the market name
    using substring matching (e.g. "Lasalgaon" → "Lasalgaon(Niphad)")
    only when the resolution is unambiguous (exactly one candidate).

    NO fallback to district or state-level data is performed.
    Forecasting must always use market-specific data only.

    Parameters
    ----------
    df : pd.DataFrame
        Combined/cleaned DataFrame from load_combined_data().
    commodity : str
        Crop/commodity name (e.g. "Tomato").
    state : str
        State name (e.g. "Maharashtra").
    district : str
        District name (e.g. "Nashik").
    market : str
        Market name (e.g. "Pimpalgaon" or "Pimpalgaon APMC").

    Returns
    -------
    dict with keys:
        "data"             : pd.DataFrame — filtered and sorted records
        "source"           : str — description of data source used
        "record_count"     : int — number of records
        "message"          : str or None — informational message
        "resolved_market"  : str — the actual market name used
        "available_markets": list or None — valid market names (shown on failure)
    """
    messages = []

    # --- Helper: case-insensitive match ---
    def _match(col, value):
        return df[col].str.lower() == value.strip().lower()

    # --- Normalize the user-supplied market name (strip APMC suffix) ---
    market_normalized = _APMC_RE.sub("", market.strip()).strip()

    # --- Base filter: commodity + state + district ---
    base_mask = (
        _match(config.COL_COMMODITY, commodity)
        & _match(config.COL_STATE, state)
        & _match(config.COL_DISTRICT, district)
    )
    district_df = df[base_mask]

    # Get all available market names in this commodity/state/district
    available_markets = sorted(
        district_df[config.COL_MARKET].str.strip().unique().tolist()
    )

    # --- 1. Try exact match on normalized market name ---
    market_lower = market_normalized.lower()
    exact_mask = base_mask & (df[config.COL_MARKET].str.lower() == market_lower)
    market_df = df[exact_mask].copy().sort_values(config.COL_DATE)
    resolved_market = market_normalized

    # --- 2. If no exact match, try fuzzy (substring) resolution ---
    if len(market_df) == 0:
        candidates = [
            m for m in available_markets
            if m.lower().startswith(market_lower) or market_lower in m.lower()
        ]

        if len(candidates) == 1:
            # Unambiguous match — resolve automatically
            resolved_market = candidates[0]
            fuzzy_mask = base_mask & (
                df[config.COL_MARKET].str.lower() == resolved_market.lower()
            )
            market_df = df[fuzzy_mask].copy().sort_values(config.COL_DATE)
            messages.append(
                f"Resolved '{market}' -> '{resolved_market}'."
            )
        elif len(candidates) > 1:
            messages.append(
                f"Market '{market}' is ambiguous. "
                f"Did you mean one of: {', '.join(candidates)}?"
            )
        # else: no candidates found

    # --- 3. Check if we have enough data ---
    if len(market_df) >= config.MIN_RECORDS:
        return {
            "data": market_df,
            "source": f"Market: {resolved_market}",
            "record_count": len(market_df),
            "message": "\n".join(messages) if messages else None,
            "resolved_market": resolved_market,
            "available_markets": None,
        }

    # --- Insufficient data — no fallback ---
    if len(market_df) > 0:
        messages.append(
            f"Market '{resolved_market}' has only {len(market_df)} record(s) "
            f"(minimum {config.MIN_RECORDS} needed)."
        )
    else:
        messages.append(
            f"No records found for market '{market}' "
            f"in {district}, {state} for commodity '{commodity}'."
        )

    if available_markets:
        messages.append(
            f"Available markets for {commodity} in {district}, {state}:\n"
            + "  " + "\n  ".join(available_markets)
        )

    messages.append("Insufficient market-specific data for forecasting.")

    return {
        "data": market_df,
        "source": "Insufficient data",
        "record_count": len(market_df),
        "message": "\n".join(messages),
        "resolved_market": resolved_market,
        "available_markets": available_markets,
    }


# =============================================================================
# prepare_context
# =============================================================================

def prepare_context(market_df):
    """
    Build the daily price time series and Chronos context tensor
    from filtered market data.

    When multiple records exist for the same date (possible when the same
    market is reported by more than one source on the same day), the daily
    median Modal_Price is used.  This is a safe, conservative aggregation
    that avoids inflating or deflating prices.

    Parameters
    ----------
    market_df : pd.DataFrame
        Filtered DataFrame from get_market_data().

    Returns
    -------
    dict with keys:
        "context_tensor" : torch.Tensor — shape (1, context_length)
        "prices"         : np.ndarray   — full daily price series
        "dates"          : pd.DatetimeIndex — corresponding dates
        "context_length" : int — number of time steps used by Chronos
    """
    # Aggregate to daily median price (handles same-date duplicates safely)
    daily = (
        market_df
        .groupby(config.COL_DATE)[config.COL_MODAL_PRICE]
        .median()
        .sort_index()
    )

    prices = daily.values.astype(float)
    dates = daily.index

    # Use up to MAX_CONTEXT_LENGTH most recent daily observations
    context_length = min(len(prices), config.MAX_CONTEXT_LENGTH)
    recent_prices = prices[-context_length:]
    recent_dates = dates[-context_length:]

    context_tensor = torch.tensor(
        recent_prices,
        dtype=torch.float32,
    ).unsqueeze(0)

    return {
        "context_tensor": context_tensor,
        "prices": prices,
        "dates": dates,
        "context_length": context_length,
        "recent_dates": recent_dates,
    }
