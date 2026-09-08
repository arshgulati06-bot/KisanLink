"""
KisanLink Backend — ML Forecast API Server
============================================
Minimal Flask API that exposes the existing ML forecasting pipeline
to the frontend. No ML logic is implemented here — it delegates
entirely to the frozen ml/ package.

Endpoints:
  GET  /api/commodities                         → unique crop list
  GET  /api/states?commodity=X                   → states for crop
  GET  /api/districts?commodity=X&state=Y        → districts
  GET  /api/markets?commodity=X&state=Y&district=Z → markets
  POST /api/forecast                             → 7-day Chronos forecast

Start:
  python backend/app.py
  → serves API on http://localhost:5000
  → serves frontend on http://localhost:5000/ (static files)
"""

import sys
import os

# Ensure the project root is on sys.path so `ml` package is importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from ml.data_loader import load_data, clean_data, get_market_data, prepare_context
from ml.forecaster import load_model, forecast_prices
from ml.evaluator import evaluate_model
from ml import config as ml_config

# ═══════════════════════════════════════════════════════════════════════
# App Setup
# ═══════════════════════════════════════════════════════════════════════

app = Flask(__name__, static_folder=None)
CORS(app)

FRONTEND_DIR = os.path.join(_PROJECT_ROOT, "frontend")

# ═══════════════════════════════════════════════════════════════════════
# Startup: Load data + model ONCE
# ═══════════════════════════════════════════════════════════════════════

print("[KisanLink API] Loading and cleaning dataset...")
_df = clean_data(load_data())
print(f"[KisanLink API] Dataset ready: {len(_df):,} records.")

print("[KisanLink API] Loading Chronos model (this may take a moment)...")
_pipeline = load_model()
print("[KisanLink API] Chronos model loaded and cached.")

# ═══════════════════════════════════════════════════════════════════════
# Static Frontend Serving
# ═══════════════════════════════════════════════════════════════════════

@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(FRONTEND_DIR, path)

# ═══════════════════════════════════════════════════════════════════════
# Cascading Dropdown Endpoints
# ═══════════════════════════════════════════════════════════════════════

@app.route("/api/commodities", methods=["GET"])
def get_commodities():
    """Return sorted list of unique commodities in the dataset."""
    commodities = sorted(_df[ml_config.COL_COMMODITY].unique().tolist())
    return jsonify(commodities)


@app.route("/api/states", methods=["GET"])
def get_states():
    """Return sorted list of states for a given commodity."""
    commodity = request.args.get("commodity", "").strip()
    if not commodity:
        return jsonify({"error": "Missing 'commodity' parameter."}), 400

    mask = _df[ml_config.COL_COMMODITY].str.lower() == commodity.lower()
    states = sorted(_df.loc[mask, ml_config.COL_STATE].unique().tolist())
    return jsonify(states)


@app.route("/api/districts", methods=["GET"])
def get_districts():
    """Return sorted list of districts for a given commodity + state."""
    commodity = request.args.get("commodity", "").strip()
    state = request.args.get("state", "").strip()
    if not commodity or not state:
        return jsonify({"error": "Missing 'commodity' or 'state' parameter."}), 400

    mask = (
        (_df[ml_config.COL_COMMODITY].str.lower() == commodity.lower())
        & (_df[ml_config.COL_STATE].str.lower() == state.lower())
    )
    districts = sorted(_df.loc[mask, ml_config.COL_DISTRICT].unique().tolist())
    return jsonify(districts)


@app.route("/api/markets", methods=["GET"])
def get_markets():
    """Return sorted list of markets for a given commodity + state + district."""
    commodity = request.args.get("commodity", "").strip()
    state = request.args.get("state", "").strip()
    district = request.args.get("district", "").strip()
    if not commodity or not state or not district:
        return jsonify({"error": "Missing required parameter(s)."}), 400

    mask = (
        (_df[ml_config.COL_COMMODITY].str.lower() == commodity.lower())
        & (_df[ml_config.COL_STATE].str.lower() == state.lower())
        & (_df[ml_config.COL_DISTRICT].str.lower() == district.lower())
    )
    markets = sorted(_df.loc[mask, ml_config.COL_MARKET].unique().tolist())
    return jsonify(markets)

# ═══════════════════════════════════════════════════════════════════════
# Forecast Endpoint
# ═══════════════════════════════════════════════════════════════════════

@app.route("/api/forecast", methods=["POST"])
def forecast():
    """
    Run the Chronos forecasting pipeline for a specific market.

    Request JSON:
      { "commodity": "Tomato", "state": "Maharashtra",
        "district": "Nashik", "market": "Pimpalgaon" }

    Response JSON on success (200):
      { "success": true, "commodity": ..., "forecast": [...], "evaluation": {...}, ... }

    Response JSON on failure (422):
      { "success": false, "error": "...", "available_markets": [...] }
    """
    data = request.get_json(silent=True) or {}

    commodity = (data.get("commodity") or "").strip()
    state = (data.get("state") or "").strip()
    district = (data.get("district") or "").strip()
    market = (data.get("market") or "").strip()

    # Validate required fields
    missing = [f for f, v in [("commodity", commodity), ("state", state),
                               ("district", district), ("market", market)] if not v]
    if missing:
        return jsonify({
            "success": False,
            "error": f"Missing required field(s): {', '.join(missing)}"
        }), 400

    # ── Filter market data using existing pipeline ──
    market_result = get_market_data(_df, commodity, state, district, market)

    if market_result["source"] == "Insufficient data":
        return jsonify({
            "success": False,
            "error": market_result.get("message", "Insufficient market-specific data."),
            "available_markets": market_result.get("available_markets") or []
        }), 422

    # ── Prepare context ──
    try:
        ctx = prepare_context(market_result["data"])
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Failed to prepare forecast context: {str(e)}"
        }), 500

    # ── Generate forecast using cached model ──
    try:
        forecast_values = forecast_prices(_pipeline, ctx["context_tensor"])
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Forecast generation failed: {str(e)}"
        }), 500

    # ── Evaluate model ──
    eval_result = evaluate_model(_pipeline, ctx["prices"])

    # ── Build response ──
    resolved = market_result.get("resolved_market", market)

    response = {
        "success": True,
        "commodity": commodity,
        "state": state,
        "district": district,
        "market": resolved,
        "data_source": market_result["source"],
        "historical_records": market_result["record_count"],
        "date_range": {
            "start": str(ctx["dates"].min().date()),
            "end": str(ctx["dates"].max().date()),
        },
        "context_length": ctx["context_length"],
        "forecast": [
            {"day": i + 1, "price": round(float(p), 2)}
            for i, p in enumerate(forecast_values)
        ],
        "evaluation": None,
    }

    if market_result.get("message"):
        response["message"] = market_result["message"]

    if eval_result is not None:
        response["evaluation"] = {
            "mae": round(float(eval_result["mae"]), 2),
            "rmse": round(float(eval_result["rmse"]), 2),
            "mape": round(float(eval_result["mape"]), 2),
        }

    return jsonify(response), 200

# ═══════════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("[KisanLink API] Starting server on http://localhost:5000")
    print("[KisanLink API] Frontend: http://localhost:5000/pages/farmer.html")
    app.run(host="0.0.0.0", port=5000, debug=False)
