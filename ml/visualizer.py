"""
KisanLink ML Pipeline — Visualization
=======================================
Matplotlib plots for historical prices and forecast display.
"""

import os
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server/script use
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from . import config


def _ensure_output_dir():
    """Create the outputs directory if it doesn't exist."""
    os.makedirs(config.OUTPUTS_DIR, exist_ok=True)


# =============================================================================
# plot_historical
# =============================================================================

def plot_historical(dates, prices, commodity, market, save=True):
    """
    Plot historical modal prices for a market/commodity.

    Parameters
    ----------
    dates : pd.DatetimeIndex or array-like
        Date values for the x-axis.
    prices : np.ndarray
        Modal price values.
    commodity : str
        Commodity name (for title).
    market : str
        Market name (for title).
    save : bool
        If True, saves the plot to ml/outputs/.

    Returns
    -------
    str or None
        Path to saved plot file, or None if save=False.
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    ax.plot(
        dates, prices,
        color="#2196F3",
        linewidth=1.5,
        marker="o",
        markersize=3,
        label="Modal Price (₹)",
    )

    ax.set_title(
        f"Historical Mandi Prices — {commodity} at {market}",
        fontsize=14,
        fontweight="bold",
        pad=12,
    )
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Modal Price (₹)", fontsize=11)
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    # Format x-axis dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d-%b-%Y"))
    fig.autofmt_xdate(rotation=30)

    plt.tight_layout()

    save_path = None
    if save:
        _ensure_output_dir()
        save_path = os.path.join(
            config.OUTPUTS_DIR,
            f"historical_{commodity.lower()}_{market.lower()}.png",
        )
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"  Plot saved: {save_path}")

    plt.close(fig)
    return save_path


# =============================================================================
# plot_forecast
# =============================================================================

def plot_forecast(dates, prices, forecast_values, commodity, market, save=True):
    """
    Plot historical prices with the 7-day forecast overlay.

    Parameters
    ----------
    dates : pd.DatetimeIndex or array-like
        Historical date values.
    prices : np.ndarray
        Historical modal price values.
    forecast_values : np.ndarray
        Forecasted price values (length = forecast horizon).
    commodity : str
        Commodity name (for title).
    market : str
        Market name (for title).
    save : bool
        If True, saves the plot to ml/outputs/.

    Returns
    -------
    str or None
        Path to saved plot file, or None if save=False.
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    # --- Historical ---
    ax.plot(
        dates, prices,
        color="#2196F3",
        linewidth=1.5,
        marker="o",
        markersize=3,
        label="Historical Price (₹)",
    )

    # --- Forecast dates (next N business days after last historical date) ---
    last_date = pd.Timestamp(dates[-1])
    forecast_dates = pd.date_range(
        start=last_date + pd.Timedelta(days=1),
        periods=len(forecast_values),
        freq="D",
    )

    # --- Connection line from last historical to first forecast ---
    bridge_dates = [last_date, forecast_dates[0]]
    bridge_prices = [prices[-1], forecast_values[0]]
    ax.plot(
        bridge_dates, bridge_prices,
        color="#FF9800",
        linewidth=1.5,
        linestyle="--",
        alpha=0.6,
    )

    # --- Forecast ---
    ax.plot(
        forecast_dates, forecast_values,
        color="#FF9800",
        linewidth=2,
        marker="s",
        markersize=5,
        label=f"{len(forecast_values)}-Day Forecast (₹)",
    )

    # --- Shaded forecast region ---
    ax.axvspan(
        forecast_dates[0], forecast_dates[-1],
        alpha=0.08,
        color="#FF9800",
        label="Forecast Window",
    )

    ax.set_title(
        f"Price Forecast — {commodity} at {market}",
        fontsize=14,
        fontweight="bold",
        pad=12,
    )
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Price (₹)", fontsize=11)
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d-%b-%Y"))
    fig.autofmt_xdate(rotation=30)

    plt.tight_layout()

    save_path = None
    if save:
        _ensure_output_dir()
        save_path = os.path.join(
            config.OUTPUTS_DIR,
            f"forecast_{commodity.lower()}_{market.lower()}.png",
        )
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"  Plot saved: {save_path}")

    plt.close(fig)
    return save_path
