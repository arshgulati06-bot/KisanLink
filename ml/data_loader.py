"""
KisanLink ML Pipeline — Data Loading & Cleaning
=================================================
Functions for loading, validating, filtering and preparing
the mandi price dataset for Chronos forecasting.
"""

import pandas as pd
import torch
import numpy as np

from . import config


# =============================================================================
# load_data
# =============================================================================

def load_data(csv_path=None):
    """
    Load the mandi price CSV into a DataFrame.

    Parameters
    ----------
    csv_path : str, optional
        Path to the CSV file. Defaults to config.DEFAULT_CSV_PATH.

    Returns
    -------
    pd.DataFrame
        Raw DataFrame as read from disk with whitespace-stripped column names.

    Raises
    ------
    FileNotFoundError
        If the CSV file does not exist at the given path.
    """
    if csv_path is None:
        csv_path = config.DEFAULT_CSV_PATH

    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    return df


# =============================================================================
# clean_data
# =============================================================================

def clean_data(df):
    """
    Validate and clean the raw mandi price DataFrame.

    Steps:
    1. Strip whitespace from all string columns (STATE, District, Market, Commodity, Variety, Grade).
    2. Parse Price Date to datetime (handles M/D/YYYY and D/M/YYYY via mixed format).
    3. Convert Min_Price, Max_Price, Modal_Price to numeric (coerce errors to NaN).
    4. Drop rows where Price Date or Modal_Price is missing/invalid.
    5. Remove exact duplicate rows.
    6. Sort by Price Date ascending.

    Parameters
    ----------
    df : pd.DataFrame
        Raw DataFrame from load_data().

    Returns
    -------
    pd.DataFrame
        Cleaned DataFrame ready for filtering.
    """
    df = df.copy()

    # --- Strip string columns ---
    str_cols = [
        config.COL_STATE,
        config.COL_DISTRICT,
        config.COL_MARKET,
        config.COL_COMMODITY,
        config.COL_VARIETY,
        config.COL_GRADE,
    ]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # --- Parse dates ---
    # The CSV uses M/D/YYYY format (e.g. 6/6/2023).
    # dayfirst=False handles this correctly.
    df[config.COL_DATE] = pd.to_datetime(
        df[config.COL_DATE],
        errors="coerce",
        dayfirst=False,
    )

    # --- Convert price columns to numeric ---
    for price_col in [config.COL_MIN_PRICE, config.COL_MAX_PRICE, config.COL_MODAL_PRICE]:
        if price_col in df.columns:
            df[price_col] = pd.to_numeric(df[price_col], errors="coerce")

    # --- Drop rows with missing critical fields ---
    df = df.dropna(subset=[config.COL_DATE, config.COL_MODAL_PRICE])

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
    Filter the dataset for a specific market.

    If no exact match is found, attempts to resolve the market name
    using substring matching (e.g. "Lasalgaon" → "Lasalgaon(Niphad)")
    only when the resolution is unambiguous (exactly one candidate).

    NO fallback to district or state-level data is performed.
    Forecasting must always use market-specific data only.

    Parameters
    ----------
    df : pd.DataFrame
        Cleaned DataFrame from clean_data().
    commodity : str
        Crop/commodity name (e.g. "Tomato").
    state : str
        State name (e.g. "Maharashtra").
    district : str
        District name (e.g. "Nashik").
    market : str
        Market name (e.g. "Pimpalgaon" or "Lasalgaon").

    Returns
    -------
    dict with keys:
        "data"             : pd.DataFrame — filtered and sorted records
        "source"           : str — description of data source used
        "record_count"     : int — number of records
        "message"          : str or None — informational message
        "resolved_market"  : str — the actual market name used (may differ from input)
        "available_markets": list or None — valid market names (shown on failure)
    """
    messages = []

    # --- Helper: case-insensitive match ---
    def _match(col, value):
        return df[col].str.lower() == value.strip().lower()

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

    # --- 1. Try exact market match ---
    market_lower = market.strip().lower()
    exact_mask = base_mask & _match(config.COL_MARKET, market)
    market_df = df[exact_mask].copy().sort_values(config.COL_DATE)
    resolved_market = market

    # --- 2. If no exact match, try fuzzy resolution ---
    if len(market_df) == 0:
        # Find markets whose name starts with or contains the user input
        candidates = [
            m for m in available_markets
            if m.lower().startswith(market_lower) or market_lower in m.lower()
        ]

        if len(candidates) == 1:
            # Unambiguous match — resolve automatically
            resolved_market = candidates[0]
            fuzzy_mask = base_mask & _match(config.COL_MARKET, resolved_market)
            market_df = df[fuzzy_mask].copy().sort_values(config.COL_DATE)
            messages.append(
                f"Resolved '{market}' -> '{resolved_market}'."
            )
        elif len(candidates) > 1:
            # Ambiguous — report candidates
            messages.append(
                f"Market '{market}' is ambiguous. "
                f"Did you mean one of: {', '.join(candidates)}?"
            )
        # else: no candidates found at all

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

    When multiple records exist for the same date (e.g. from district/state
    fallback), the daily median Modal_Price is used.

    Parameters
    ----------
    market_df : pd.DataFrame
        Filtered DataFrame from get_market_data().

    Returns
    -------
    dict with keys:
        "context_tensor" : torch.Tensor — shape (1, context_length)
        "prices"         : np.ndarray   — raw daily price series
        "dates"          : pd.DatetimeIndex — corresponding dates
        "context_length" : int — number of time steps used
    """
    # Aggregate to daily median price
    daily = (
        market_df
        .groupby(config.COL_DATE)[config.COL_MODAL_PRICE]
        .median()
        .sort_index()
    )

    prices = daily.values
    dates = daily.index

    # Use up to MAX_CONTEXT_LENGTH most recent records
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
    }
