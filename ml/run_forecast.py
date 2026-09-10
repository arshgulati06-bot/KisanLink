#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KisanLink ML Pipeline — Main Entry Point
==========================================
Run the complete mandi price forecasting pipeline.

Usage:
    python -m ml.run_forecast --commodity Tomato --state Maharashtra --district Nashik --market Pimpalgaon

    Or run directly:
    python ml/run_forecast.py --commodity Tomato --state Maharashtra --district Nashik --market Pimpalgaon
"""

import argparse
import sys
import os

# Allow running both as `python ml/run_forecast.py` and `python -m ml.run_forecast`
if __name__ == "__main__" and __package__ is None:
    _parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _parent not in sys.path:
        sys.path.insert(0, _parent)

from ml import config
from ml.data_loader import load_data, load_combined_data, clean_data, get_market_data, prepare_context
from ml.forecaster import load_model, forecast_prices
from ml.evaluator import evaluate_model
from ml.visualizer import plot_historical, plot_forecast


# =============================================================================
# Argument Parser
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="KisanLink Mandi Price Forecasting Pipeline",
    )
    parser.add_argument(
        "--commodity", type=str, required=True,
        help="Crop/commodity name (e.g. Tomato, Wheat, Potato)",
    )
    parser.add_argument(
        "--state", type=str, required=True,
        help="State name (e.g. Maharashtra)",
    )
    parser.add_argument(
        "--district", type=str, required=True,
        help="District name (e.g. Nashik)",
    )
    parser.add_argument(
        "--market", type=str, required=True,
        help="Market name (e.g. Pimpalgaon)",
    )
    parser.add_argument(
        "--csv", type=str, default=None,
        help="Path to a single CSV file (overrides default combined dataset).",
    )
    parser.add_argument(
        "--no-plots", action="store_true",
        help="Skip generating visualization plots",
    )
    return parser.parse_args()


# =============================================================================
# Main Pipeline
# =============================================================================

def run_pipeline(commodity, state, district, market, csv_path=None, generate_plots=True):
    """
    Execute the complete forecasting pipeline.

    Parameters
    ----------
    commodity : str
    state : str
    district : str
    market : str
    csv_path : str, optional
    generate_plots : bool

    Returns
    -------
    dict with keys:
        "forecast"      : list of float — 7-day forecast values
        "evaluation"    : dict or None — MAE/RMSE/MAPE metrics
        "data_source"   : str — what data was actually used
        "record_count"  : int — number of historical records
        "date_range"    : tuple of (start_date, end_date)
        "context_length": int — number of time steps fed to model
        "plots"         : dict with "historical" and "forecast" paths (or None)
        "selection"     : dict of the user's selection
    """

    result = {
        "selection": {
            "commodity": commodity,
            "state": state,
            "district": district,
            "market": market,
        },
        "forecast": None,
        "evaluation": None,
        "data_source": None,
        "record_count": 0,
        "date_range": None,
        "context_length": 0,
        "plots": {"historical": None, "forecast": None},
        "gap_info": None,
        "n_winsorized": 0,
    }

    # ── Step 1: Load Data ──
    print("\n" + "=" * 55)
    print("  KisanLink — Mandi Price Forecasting Pipeline")
    print("=" * 55)
    print(f"\n  Commodity : {commodity}")
    print(f"  State     : {state}")
    print(f"  District  : {district}")
    print(f"  Market    : {market}")
    print("-" * 55)

    if csv_path:
        # Single-file override via --csv flag
        print(f"\n[1/6] Loading single dataset: {csv_path}")
        df = load_data(csv_path)
        print(f"  Loaded {len(df):,} raw records.")
        print("\n[2/6] Cleaning data...")
        df = clean_data(df)
        print(f"  {len(df):,} records after cleaning.")
    else:
        # Default: combine all 3 datasets
        print("\n[1/6] Loading combined dataset (Agriculture + 2022 + 2026)...")
        df = load_combined_data()
        print(f"  {len(df):,} combined records loaded and normalized.")
        print("\n[2/6] (Normalization already applied during loading.)")

    # ── Step 3: Filter Market Data ──
    print("\n[3/6] Filtering market data...")
    market_result = get_market_data(df, commodity, state, district, market)

    result["data_source"] = market_result["source"]
    result["record_count"] = market_result["record_count"]

    if market_result["message"]:
        print(f"  [!] {market_result['message']}")

    if market_result["source"] == "Insufficient data":
        print(f"\n  [X] Not enough historical data for forecasting.")
        print(f"    Available records: {market_result['record_count']}")
        print(f"    Minimum required:  {config.MIN_RECORDS}")
        print("\n" + "=" * 55)
        return result

    print(f"  Data source: {market_result['source']}")
    print(f"  Records:     {market_result['record_count']}")

    # ── Step 4: Prepare Context ──
    print("\n[4/6] Preparing time series context...")
    ctx = prepare_context(market_result["data"])

    date_start = ctx["dates"].min()
    date_end = ctx["dates"].max()
    result["date_range"] = (date_start, date_end)
    result["context_length"] = ctx["context_length"]
    result["gap_info"]       = ctx.get("gap_info")
    result["n_winsorized"]   = ctx.get("n_winsorized", 0)

    print(f"  Daily price points: {len(ctx['prices'])}")
    print(f"  Context length:     {ctx['context_length']}")
    print(f"  Date range:         {date_start.date()} to {date_end.date()}")
    if ctx.get('gap_info'):
        print(f"  [GAP] {ctx['gap_info']}")
    if ctx.get('n_winsorized', 0) > 0:
        print(f"  [WINSOR] {ctx['n_winsorized']} value(s) clipped by 5*IQR fence.")

    # ── Step 5: Load Model & Forecast ──
    print("\n[5/6] Loading pretrained Chronos model...")
    pipeline = load_model()
    print("  Model loaded successfully.")

    print("\n  Generating 7-day forecast...")
    forecast_values = forecast_prices(pipeline, ctx["context_tensor"])
    result["forecast"] = forecast_values.tolist()

    # ── Step 6: Evaluate ──
    print("\n[6/6] Evaluating model...")
    eval_result = evaluate_model(pipeline, ctx["prices"])
    result["evaluation"] = eval_result

    # ═══════════════════════════════════════════════════════
    # Output
    # ═══════════════════════════════════════════════════════

    print("\n" + "=" * 55)
    print("  7-Day Price Forecast")
    print("=" * 55)
    print(f"  Commodity : {commodity}")
    print(f"  State     : {state}")
    print(f"  District  : {district}")
    print(f"  Market    : {market}")
    print(f"  Data Used : {market_result['source']}")
    print(f"  Records   : {market_result['record_count']}")
    print(f"  Date Range: {date_start.date()} to {date_end.date()}")
    print("-" * 55)

    print("\n  Forecast:")
    for i, price in enumerate(forecast_values, 1):
        print(f"    Day {i}: Rs.{price:,.2f}")

    # ── Evaluation Output ──
    print("\n" + "-" * 55)
    if eval_result is not None:
        print("  Model Evaluation (Holdout Backtest)")
        print("-" * 55)

        print("\n  Actual vs Predicted:")
        for i in range(len(eval_result["actuals"])):
            actual = eval_result["actuals"][i]
            predicted = eval_result["predicted"][i]
            print(f"    Day {i+1}: Actual Rs.{actual:,.2f}  |  Predicted Rs.{predicted:,.2f}")

        print(f"\n  MAE  : Rs.{eval_result['mae']:,.2f}")
        print(f"  RMSE : Rs.{eval_result['rmse']:,.2f}")
        print(f"  MAPE : {eval_result['mape']:.2f}%")
    else:
        print(f"  Evaluation skipped — need at least {config.MIN_EVAL_RECORDS} "
              f"daily records (have {len(ctx['prices'])}).")

    print("=" * 55)

    # ── Visualizations ──
    if generate_plots:
        print("\n  Generating plots...")
        try:
            hist_path = plot_historical(
                ctx["dates"], ctx["prices"],
                commodity, market,
            )
            result["plots"]["historical"] = hist_path

            fc_path = plot_forecast(
                ctx["dates"], ctx["prices"],
                forecast_values,
                commodity, market,
            )
            result["plots"]["forecast"] = fc_path

            print("  Plots generated successfully.")
        except Exception as e:
            print(f"  ⚠ Plot generation failed: {e}")

    print("\n" + "=" * 55)
    print("  Pipeline completed successfully.")
    print("=" * 55 + "\n")

    return result


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == "__main__":
    args = parse_args()
    run_pipeline(
        commodity=args.commodity,
        state=args.state,
        district=args.district,
        market=args.market,
        csv_path=args.csv,
        generate_plots=not args.no_plots,
    )
