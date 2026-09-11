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
from .ingest import load_ingested_frame

_COMBINED_MEMORY = None
_COMBINED_SIG = None


def _source_signature() -> str:
    paths = [
        config.CSV_AGRICULTURE,
        config.CSV_2022,
        config.CSV_2026,
        getattr(config, "INGESTED_RECORDS_PATH", ""),
    ]
    parts = []
    for path in paths:
        if path and os.path.exists(path):
            st = os.stat(path)
            parts.append(f"{os.path.basename(path)}:{int(st.st_mtime)}:{st.st_size}")
        else:
            parts.append(f"{os.path.basename(path) if path else 'missing'}:0:0")
    return "|".join(parts)


def invalidate_combined_cache():
    """Drop in-memory and on-disk combined cache (called after ingest)."""
    global _COMBINED_MEMORY, _COMBINED_SIG
    _COMBINED_MEMORY = None
    _COMBINED_SIG = None
    for path in (config.COMBINED_CACHE_PATH, config.COMBINED_CACHE_SIG):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def _add_filter_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_commodity_l"] = df[config.COL_COMMODITY].astype(str).str.lower()
    df["_state_l"] = df[config.COL_STATE].astype(str).str.lower()
    df["_district_l"] = df[config.COL_DISTRICT].astype(str).str.lower()
    df["_market_l"] = df[config.COL_MARKET].astype(str).str.lower()
    return df


def _write_cache(df: pd.DataFrame, sig: str) -> None:
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        df.to_pickle(config.COMBINED_CACHE_PATH)
        with open(config.COMBINED_CACHE_SIG, "w", encoding="utf-8") as f:
            f.write(sig)
    except (OSError, MemoryError):
        pass


def _read_cache(sig: str):
    if not os.path.exists(config.COMBINED_CACHE_PATH) or not os.path.exists(config.COMBINED_CACHE_SIG):
        return None
    try:
        with open(config.COMBINED_CACHE_SIG, encoding="utf-8") as f:
            if f.read().strip() != sig:
                return None
        return pd.read_pickle(config.COMBINED_CACHE_PATH)
    except Exception:
        return None


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
    try:
        df[config.COL_DATE] = pd.to_datetime(
            df[config.COL_DATE], errors="coerce", format="mixed"
        )
    except (TypeError, ValueError):
        df[config.COL_DATE] = pd.to_datetime(
            df[config.COL_DATE], errors="coerce", dayfirst=False
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

def load_combined_data(use_cache: bool = True) -> pd.DataFrame:
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
    global _COMBINED_MEMORY, _COMBINED_SIG
    sig = _source_signature()
    if use_cache and _COMBINED_MEMORY is not None and _COMBINED_SIG == sig:
        return _COMBINED_MEMORY
    if use_cache:
        cached = _read_cache(sig)
        if cached is not None and not cached.empty:
            _COMBINED_MEMORY = cached
            _COMBINED_SIG = sig
            return cached

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

    ingested = load_ingested_frame()
    if ingested is not None and not ingested.empty:
        keep = [c for c in combined.columns if c in ingested.columns]
        if keep:
            combined = pd.concat([combined, ingested[keep]], ignore_index=True)

    # Remove exact duplicates (same row across datasets)
    combined = combined.drop_duplicates()

    # Sort chronologically
    combined = combined.sort_values(config.COL_DATE).reset_index(drop=True)
    combined = _add_filter_columns(combined)

    if use_cache:
        _write_cache(combined, sig)
        _COMBINED_MEMORY = combined
        _COMBINED_SIG = sig

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
    return _add_filter_columns(df)


def _market_equals_mask(df: pd.DataFrame, base_mask, market_lower: str):
    """Case-insensitive market equality; uses precomputed _market_l when present."""
    if "_market_l" in df.columns:
        return base_mask & (df["_market_l"] == market_lower)
    return base_mask & (df[config.COL_MARKET].astype(str).str.lower() == market_lower)


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
    def _match(col, value, lcol=None):
        needle = value.strip().lower()
        if lcol and lcol in df.columns:
            return df[lcol] == needle
        return df[col].astype(str).str.lower() == needle

    # --- Normalize the user-supplied market name (strip APMC suffix) ---
    market_normalized = _APMC_RE.sub("", market.strip()).strip()

    # --- Base filter: commodity + state + district ---
    base_mask = (
        _match(config.COL_COMMODITY, commodity, "_commodity_l")
        & _match(config.COL_STATE, state, "_state_l")
        & _match(config.COL_DISTRICT, district, "_district_l")
    )
    district_df = df[base_mask]

    # Get all available market names in this commodity/state/district
    available_markets = sorted(
        district_df[config.COL_MARKET].str.strip().unique().tolist()
    )

    # --- 1. Try exact match on normalized market name ---
    market_lower = market_normalized.lower()
    market_df = df[_market_equals_mask(df, base_mask, market_lower)].copy().sort_values(config.COL_DATE)
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
            market_df = df[_market_equals_mask(
                df, base_mask, resolved_market.lower()
            )].copy().sort_values(config.COL_DATE)
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
# prepare_context helpers
# =============================================================================

def _truncate_at_gap(prices, dates, max_gap_days, min_records):
    """
    Find the most recent usable continuous price segment of the daily series.

    When different source datasets cover completely different price eras
    (e.g. 2022.csv flower prices in one unit vs 2026.csv at a completely
    different scale, separated by a multi-year gap), combining them produces
    a non-stationary series that corrupts Chronos forecasting.

    Algorithm (smarter reversed-gap walk):
    ----------------------------------------
    1. Compute inter-observation day gaps for the chronologically sorted series.
    2. Collect all gap positions where the gap exceeds ``max_gap_days``.
    3. Walk through those positions from MOST RECENT to OLDEST.
       For each gap position G, the candidate segment is prices[G:].
       Pick the FIRST (most recent) candidate whose length >= min_records.
    4. If no single post-gap candidate has enough observations, return the
       full series so the market remains usable — and report why.

    This strategy ensures:
    - Latest coherent data is preferred over older eras.
    - A tiny 2026.csv segment (e.g. 11 obs) that follows a large gap is skipped
      if the next older gap creates a segment with sufficient observations.
    - No valid market is silently rejected just because of data availability issues.

    Parameters
    ----------
    prices       : np.ndarray        — chronologically sorted daily prices
    dates        : pd.DatetimeIndex  — corresponding dates (same length)
    max_gap_days : int               — gap threshold; only gaps longer than this qualify
    min_records  : int               — minimum observations a candidate segment must have

    Returns
    -------
    (prices, dates, gap_info)
        prices, dates : selected segment (or full series as fallback)
        gap_info      : human-readable string describing what was done, or None
    """
    if len(prices) < 2:
        return prices, dates, None

    date_series = pd.Series(dates)
    day_diffs = date_series.diff().fillna(pd.Timedelta(0)).dt.days

    # All positions where the gap between consecutive obs > max_gap_days
    gap_positions = [
        i for i in range(1, len(day_diffs))
        if day_diffs.iloc[i] > max_gap_days
    ]

    if not gap_positions:
        return prices, dates, None

    # Walk from most recent gap to oldest; pick first candidate with enough obs
    for gp in reversed(gap_positions):
        seg_prices = prices[gp:]
        seg_dates  = dates[gp:]
        gap_days   = int(day_diffs.iloc[gp])

        if len(seg_prices) >= min_records:
            info = (
                f"Gap of {gap_days} days detected before {seg_dates[0].date()}; "
                f"using the {len(seg_prices)} most-recent observations "
                f"({seg_dates[0].date()} to {seg_dates[-1].date()}) "
                f"to avoid cross-era price contamination."
            )
            return seg_prices, seg_dates, info

    # All post-gap segments are too short — fall back to the full series
    gap_summaries = ", ".join(
        f"{int(day_diffs.iloc[gp])}d at {dates[gp].date()}"
        for gp in gap_positions
    )
    info = (
        f"Gaps detected ({gap_summaries}), but every post-gap segment has "
        f"fewer than {min_records} observations; using the full {len(prices)}-obs series."
    )
    return prices, dates, info



def _winsorize_prices(prices, k):
    """
    Return a copy of ``prices`` with extreme outliers clipped to
    (max(0, Q1 - k*IQR), Q3 + max(k*IQR, k*Q3)).

    The upper fence uses ``max(k*IQR, k*Q3)`` so that when IQR = 0 (e.g. a
    series where every day has exactly the same price except one corrupted row),
    the fence falls back to k * Q3 instead of Q3 + 0 = Q3, which would
    clip everything above the median.  This ensures genuine data-entry errors
    like Rs.191,820,849 in an otherwise Rs.1,000 series are still caught.

    k=5.0 (config.OUTLIER_IQR_K) is very conservative: it removes only
    genuine data-entry errors while leaving all legitimately high prices
    untouched (e.g. Rs.220,000/quintal for exotic flowers is well inside
    the 5×IQR fence for that market's price distribution).

    The winsorization is applied only to the series fed to Chronos;
    the raw database records are never modified.

    Returns a new np.ndarray of the same length.
    """
    if len(prices) < 4:
        return prices.copy()
    q1, q3 = np.percentile(prices, 25), np.percentile(prices, 75)
    iqr = q3 - q1
    lo = max(q1 - k * iqr, 0.0) if iqr > 0 else 0.0
    # When IQR = 0 (constant series), k*IQR = 0 and lo=q1 would clip ALL prices
    # below Q1 up to Q1, destroying ALL variation in the series → flat context →
    # flat Chronos forecast.  Fix: set lo=0 when IQR=0 (only cap the upper end).
    hi = q3 + max(k * iqr, k * q3 if q3 > 0 else 0.0)
    return np.clip(prices, lo, hi)



# =============================================================================
# prepare_context
# =============================================================================

def prepare_context(market_df):
    """
    Build the daily price time series and Chronos context tensor
    from filtered market data.

    Pipeline
    --------
    1. **Daily aggregation**: group by date, take the median Modal_Price
       (handles same-date duplicates from overlapping source CSVs safely).

    2. **Gap detection** (config.MAX_GAP_DAYS = 365 days by default):
       if the daily series has a gap longer than MAX_GAP_DAYS, only the
       most recent continuous segment is retained.  This prevents cross-era
       price contamination when a market appears in 2022.csv with one price
       scale and in 2026.csv at a completely different level (e.g. Raibel
       flowers at Flower Market,Gazipur have a 1100-day gap and prices that
       differ by ~100x between the two eras).

    3. **Winsorization** (config.OUTLIER_IQR_K = 5.0 by default):
       clip the segment at the (Q1 - 5*IQR, Q3 + 5*IQR) fence.  This
       neutralises genuine data-entry errors (e.g. the Rs.191,820,849 row
       found in the raw dataset) without touching legitimate high prices
       such as Rs.220,000/quintal for exotic flowers.

    4. **Context window**: use the most recent config.MAX_CONTEXT_LENGTH
       (= 150) observations of the clean series as the Chronos input.

    The ``prices`` and ``dates`` keys in the returned dict reflect the
    gap-truncated, winsorized series so that evaluate_model() uses exactly
    the same data for consistent backtesting.

    Parameters
    ----------
    market_df : pd.DataFrame
        Filtered DataFrame from get_market_data().

    Returns
    -------
    dict with keys:
        "context_tensor" : torch.Tensor — shape (1, context_length)
        "prices"         : np.ndarray   — clean daily price series
                                          (post gap-truncation, post-winsorization)
        "dates"          : pd.DatetimeIndex — dates of the clean series
        "context_length" : int — number of time steps fed to Chronos
        "recent_dates"   : pd.DatetimeIndex — dates of the context window
        "gap_info"       : str or None — human-readable gap message (if truncation occurred)
        "n_winsorized"   : int — number of values changed by winsorization (0 = no effect)
    """
    # ------------------------------------------------------------------
    # Step 1: Daily median aggregation
    # ------------------------------------------------------------------
    daily = (
        market_df
        .groupby(config.COL_DATE)[config.COL_MODAL_PRICE]
        .median()
        .sort_index()
    )

    prices_raw = daily.values.astype(float)
    dates_raw  = daily.index

    # ------------------------------------------------------------------
    # Step 2: Gap-based truncation
    # ------------------------------------------------------------------
    prices, dates, gap_info = _truncate_at_gap(
        prices_raw, dates_raw,
        max_gap_days=config.MAX_GAP_DAYS,
        min_records=config.MIN_RECORDS,
    )

    # ------------------------------------------------------------------
    # Step 3: Conservative winsorization
    # ------------------------------------------------------------------
    prices_clean = _winsorize_prices(prices, k=config.OUTLIER_IQR_K)
    n_winsorized = int(np.sum(prices_clean != prices))

    # ------------------------------------------------------------------
    # Step 4: Context window
    # ------------------------------------------------------------------
    context_length = min(len(prices_clean), config.MAX_CONTEXT_LENGTH)
    recent_prices  = prices_clean[-context_length:]
    recent_dates   = dates[-context_length:]

    context_tensor = torch.tensor(
        recent_prices,
        dtype=torch.float32,
    ).unsqueeze(0)

    return {
        "context_tensor": context_tensor,
        "prices":         prices_clean,
        "dates":          dates,
        "context_length": context_length,
        "recent_dates":   recent_dates,
        "gap_info":       gap_info,
        "n_winsorized":   n_winsorized,
    }
