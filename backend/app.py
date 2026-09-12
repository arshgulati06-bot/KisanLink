"""
KisanLink Backend — ML Forecast API Server + Persistent Application DB
=======================================================================
Flask API for Chronos forecasting, market intel, buyer matching, ingestion,
authentication, and user/lot/offer/transaction persistence.

Two independent data layers:
  1. ML / Chronos: historical mandi CSVs → forecast → sale window
  2. Application DB: SQLite (kisanlink.sqlite3) → users, lots, offers, etc.

Historical mandi CSV data is NOT in the application DB.
No hardcoded market prices or forecast values.
"""

import os
import sys
import threading

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from flask import Flask, jsonify, request, send_from_directory, current_app
from flask_cors import CORS

import pandas as pd
import numpy as np

from ml.data_loader import load_combined_data, get_market_data, prepare_context
from ml.forecaster import load_model, forecast_with_quantiles
from ml.evaluator import evaluate_model
from ml.decision_engine import recommend_sale_window
from ml.buyer_matcher import match_buyers
from ml.price_sanity import sanitize_forecast
from ml.transport import (
    estimate_distance_km,
    net_realisation,
    transport_loading_rate,
    transport_rate,
    verified_district_coords,
)
from ml.ingest import (
    ingest_records,
    official_api_configured,
    fetch_official_records,
    load_buyer_demands,
)
from ml import config as ml_config
from ml import dev_fixture

# ---------------------------------------------------------------------------
# Application DB + Auth (SQLite-backed, no external DB server required)
# ---------------------------------------------------------------------------
# kl_db.py, kl_auth.py, kl_user_repo.py, kl_lot_repo.py are in the same
# directory as this file (backend/). Direct imports work without any conflict.
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import kl_db as _app_db
import kl_auth as _auth
import kl_user_repo as _user_repo
import kl_lot_repo as _lot_repo

from services.mandi_live import fetch_live_prices
from services.geocode import reverse_geocode, geocode_market, validate_coords, external_http_allowed
from services.routing import compute_route

FRONTEND_DIR = os.path.join(_PROJECT_ROOT, "frontend")
_STORE_LOCK = threading.Lock()
_INIT_LOCK = threading.Lock()
_REAL_APP = None


def _public_error(message, status=400, **extra):
    body = {"success": False, "error": message}
    body.update(extra)
    return jsonify(body), status


def _store():
    return current_app.extensions["kisanlink"]


def _df():
    return _store()["df"]


def _pipeline():
    return _store()["pipeline"]


def _mask_commodity_state_district(df, commodity, state, district=None):
    if df.empty or "_commodity_l" not in df.columns:
        return pd.Series(False, index=df.index)
    mask = (
        (df["_commodity_l"] == commodity.strip().lower())
        & (df["_state_l"] == state.strip().lower())
    )
    if district:
        mask = mask & (df["_district_l"] == district.strip().lower())
    return mask


def _dev_fixture_active():
    try:
        return bool(_store().get("dev_fixture"))
    except Exception:
        return False


def _source_label():
    if _dev_fixture_active():
        return dev_fixture.SOURCE_LABEL
    if official_api_configured():
        return "Combined historical CSVs plus configured official API ingest"
    return "Combined historical mandi CSVs (local files). Live official API is not configured."


def _allow_external_http():
    if current_app.config.get("TESTING"):
        return False
    return external_http_allowed()


def _optional_lat_lon(payload):
    lat = payload.get("lat", payload.get("latitude"))
    lon = payload.get("lon", payload.get("longitude", payload.get("lng")))
    if lat in (None, "") and lon in (None, ""):
        return None, None, None
    if lat in (None, "") or lon in (None, ""):
        return None, None, "Both lat and lon are required when providing GPS coordinates."
    lat_f, lon_f, err = validate_coords(lat, lon)
    if err:
        return None, None, err
    return lat_f, lon_f, None


def _freshness_fields(latest_date, is_live_price: bool):
    days_old = int((pd.Timestamp.today().normalize() - pd.Timestamp(latest_date).normalize()).days)
    if is_live_price:
        label = "TODAY'S LIVE MANDI DATA"
    elif days_old > 30:
        label = "HISTORICAL DATA"
    elif days_old == 0:
        label = "LATEST AVAILABLE MANDI DATA"
    else:
        label = "LATEST AVAILABLE MANDI DATA"
    return days_old, label


def _confidence_payload(ctx, latest_date):
    days_old = int((pd.Timestamp.today().normalize() - pd.Timestamp(latest_date).normalize()).days)
    n = ctx["context_length"]
    if n >= 60:
        label = "Good"
    elif n >= 25:
        label = "Moderate"
    else:
        label = "Low"
    stale = days_old > 7
    return {
        "label": label,
        "context_length": n,
        "gap_detected": bool(ctx.get("gap_info")),
        "n_winsorized": int(ctx.get("n_winsorized", 0)),
        "days_since_last_record": days_old,
        "stale_data": stale,
        "note": (
            f"Latest observation in the dataset is {latest_date.date() if hasattr(latest_date, 'date') else latest_date} "
            f"({days_old} day(s) before today). This is not a live 'today' mandi quote."
            if stale else
            f"Latest observation date: {latest_date.date() if hasattr(latest_date, 'date') else latest_date}."
        ),
    }


def _ingest_authorized():
    token = ml_config.INGEST_TOKEN
    if not token:
        return bool(current_app.config.get("TESTING", False))
    header = request.headers.get("Authorization", "")
    provided = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not provided:
        provided = request.headers.get("X-KisanLink-Ingest-Token", "").strip()
    return provided == token


def _init_database():
    """
    Initialise the SQLite application database.

    Called once at startup.  Failures are logged but do NOT crash the server;
    the ML/Chronos pipeline runs independently of the application DB.
    """
    try:
        ok = _app_db.init_schema()
        if ok:
            print("[KisanLink DB] Application database ready.")
        else:
            print("[KisanLink DB] WARNING: schema init returned False. Check database/schema.sql.")
    except Exception as exc:
        print(f"[KisanLink DB] WARNING: Could not initialise application database: {exc}")
        print("[KisanLink DB]   The ML forecast API will still work without the application DB.")


def create_app(dataframe=None, pipeline=None, load_real_data=True, load_chronos=True):
    app = Flask(__name__, static_folder=None)
    CORS(app)
    app.config["MAX_CONTENT_LENGTH"] = ml_config.INGEST_MAX_BYTES
    app.config["JSON_SORT_KEYS"] = False

    using_dev_fixture = False
    if dataframe is None and load_real_data:
        print("[KisanLink API] Loading combined mandi datasets (cache used when valid)...")
        try:
            dataframe = load_combined_data()
            print(
                f"[KisanLink API] Combined dataset ready: {len(dataframe):,} records, "
                f"{dataframe[ml_config.COL_COMMODITY].nunique()} commodities."
            )
        except FileNotFoundError:
            if not dev_fixture.enabled():
                raise
            # Explicit opt-in only. Never silently substitutes synthetic rows.
            dataframe = dev_fixture.build_frame()
            using_dev_fixture = True
            print("[KisanLink API] " + "=" * 62)
            print("[KisanLink API] HISTORICAL CSVs NOT FOUND — running on the")
            print("[KisanLink API] SYNTHETIC DEVELOPMENT FIXTURE.")
            print("[KisanLink API] These are generated sample rows, NOT real or")
            print("[KisanLink API] government mandi data. Responses are labelled")
            print("[KisanLink API] dev_fixture=true so the UI shows a warning.")
            print("[KisanLink API] " + "=" * 62)
    elif dataframe is None:
        dataframe = pd.DataFrame()

    from ml.data_loader import _add_filter_columns
    if dataframe is not None and not dataframe.empty and "_commodity_l" not in dataframe.columns:
        dataframe = _add_filter_columns(dataframe)

    if pipeline is None and load_chronos:
        print("[KisanLink API] Loading Chronos model...")
        pipeline = load_model()
        print("[KisanLink API] Chronos model loaded.")

    buyers, buyer_note = load_buyer_demands()
    latest = None
    if dataframe is not None and not dataframe.empty:
        latest = str(pd.to_datetime(dataframe[ml_config.COL_DATE]).max().date())

    app.extensions["kisanlink"] = {
        "df": dataframe,
        "dev_fixture": using_dev_fixture,
        "pipeline": pipeline,
        "buyers": buyers,
        "buyer_note": buyer_note,
        "ingestion_meta": {
            "last_update": None,
            "total_records": 0 if dataframe is None else len(dataframe),
            "latest_date_in_dataset": latest,
            "live_api_connected": official_api_configured(),
            "sources": [
                {"name": "SYNTHETIC DEVELOPMENT FIXTURE", "type": "synthetic"},
            ] if using_dev_fixture else [
                {"name": "Agriculture_price_dataset.csv", "type": "historical"},
                {"name": "2022.csv", "type": "historical"},
                {"name": "2026.csv", "type": "historical"},
                {"name": "ingested/records.csv", "type": "incremental"},
            ],
        },
    }

    _init_database()
    register_routes(app)
    return app


def _create_farmer_offer(user_id, data):
    """A farmer offers one of their own lots against an open buyer requirement."""
    requirement_id = data.get("requirement_id")
    if not requirement_id:
        return _public_error(
            "'requirement_id' is required: a farmer offer is made against an "
            "open buyer requirement."
        )
    try:
        requirement_id = int(requirement_id)
    except (TypeError, ValueError):
        return _public_error("Invalid 'requirement_id'.")

    requirement = _lot_repo.get_requirement_by_id(requirement_id)
    if not requirement:
        return _public_error("Buyer requirement not found.", 404)
    if str(requirement.get("status", "OPEN")).upper() != "OPEN":
        return _public_error("That buyer requirement is no longer open.", 409)

    lot_id = data.get("lot_id")
    if not lot_id:
        return _public_error("'lot_id' is required: choose which of your lots to offer.")
    try:
        lot = _lot_repo.get_lot_by_id(int(lot_id))
    except (TypeError, ValueError):
        return _public_error("Invalid 'lot_id'.")
    if not lot:
        return _public_error("Lot not found.", 404)
    if lot.get("farmer_user_id") != user_id:
        return _public_error("You can only offer your own lots.", 403)

    # `x or default` would turn an explicit 0 into the lot quantity, so only an
    # absent value falls back.
    raw_qty = data.get("quantity_qtl")
    if raw_qty in (None, ""):
        raw_qty = lot.get("quantity_qtl")
    try:
        price = float(data.get("price_per_qtl") or 0)
        qty = float(raw_qty or 0)
    except (TypeError, ValueError):
        return _public_error("'price_per_qtl' and 'quantity_qtl' must be numbers.")
    if price <= 0:
        return _public_error("'price_per_qtl' must be greater than zero.")
    if qty <= 0:
        return _public_error("'quantity_qtl' must be greater than zero.")

    try:
        offer_id = _lot_repo.create_offer(
            buyer_user_id=requirement["buyer_user_id"],
            seller_user_id=user_id,
            lot_id=lot["id"],
            data={**data, "requirement_id": requirement_id,
                  "price_per_qtl": price, "quantity_qtl": qty},
            initiated_by="FARMER",
        )
        return jsonify({
            "success": True,
            "offer_id": offer_id,
            "initiated_by": "FARMER",
            "message": "Offer sent to the buyer.",
        }), 201
    except Exception as exc:
        print(f"[DB] farmer create_offer error: {exc}")
        return _public_error("Could not save offer.", 500)


def register_routes(app):
    @app.route("/")
    def serve_index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.route("/<path:path>")
    def serve_static(path):
        return send_from_directory(FRONTEND_DIR, path)

    @app.route("/api/commodities", methods=["GET"])
    def get_commodities():
        df = _df()
        if df.empty or ml_config.COL_COMMODITY not in df.columns:
            return jsonify([])
        commodities = sorted(df[ml_config.COL_COMMODITY].dropna().unique().tolist())
        return jsonify(commodities)

    @app.route("/api/states", methods=["GET"])
    def get_states():
        commodity = request.args.get("commodity", "").strip()
        if not commodity:
            return _public_error("Missing 'commodity' parameter.")
        df = _df()
        if df.empty or "_commodity_l" not in df.columns:
            return jsonify([])
        mask = df["_commodity_l"] == commodity.lower()
        states = sorted(df.loc[mask, ml_config.COL_STATE].dropna().unique().tolist())
        return jsonify(states)

    @app.route("/api/districts", methods=["GET"])
    def get_districts():
        commodity = request.args.get("commodity", "").strip()
        state = request.args.get("state", "").strip()
        if not commodity or not state:
            return _public_error("Missing 'commodity' or 'state' parameter.")
        df = _df()
        mask = _mask_commodity_state_district(df, commodity, state)
        districts = sorted(df.loc[mask, ml_config.COL_DISTRICT].dropna().unique().tolist())
        return jsonify(districts)

    @app.route("/api/markets", methods=["GET"])
    def get_markets():
        commodity = request.args.get("commodity", "").strip()
        state = request.args.get("state", "").strip()
        district = request.args.get("district", "").strip()
        if not commodity or not state or not district:
            return _public_error("Missing required parameter(s).")
        df = _df()
        mask = _mask_commodity_state_district(df, commodity, state, district)
        markets = sorted(df.loc[mask, ml_config.COL_MARKET].dropna().unique().tolist())
        return jsonify(markets)

    @app.route("/api/forecast", methods=["POST"])
    def forecast():
        data = request.get_json(silent=True) or {}
        commodity = (data.get("commodity") or "").strip()
        state = (data.get("state") or "").strip()
        district = (data.get("district") or "").strip()
        market = (data.get("market") or "").strip()
        try:
            quantity_qtl = float(data.get("quantity_qtl", 10) or 10)
            storage_cost_per_day = float(data.get("storage_cost_per_day", 0) or 0)
        except (TypeError, ValueError):
            return _public_error("quantity_qtl and storage_cost_per_day must be numeric.")

        missing = [f for f, v in [
            ("commodity", commodity), ("state", state),
            ("district", district), ("market", market),
        ] if not v]
        if missing:
            return _public_error(f"Missing required field(s): {', '.join(missing)}")

        pipe = _pipeline()
        if pipe is None:
            return _public_error("Forecast model is not loaded.", 503)

        market_result = get_market_data(_df(), commodity, state, district, market)
        if market_result["source"] == "Insufficient data":
            return _public_error(
                market_result.get("message", "Insufficient market-specific data."),
                422,
                available_markets=market_result.get("available_markets") or [],
            )

        try:
            ctx = prepare_context(market_result["data"])
            fc = forecast_with_quantiles(pipe, ctx["context_tensor"])
        except Exception:
            return _public_error("Forecast generation failed. Try again or pick another market.", 500)

        latest_date = ctx["dates"].max()
        raw_latest_rows = market_result["data"].loc[
            market_result["data"][ml_config.COL_DATE] == market_result["data"][ml_config.COL_DATE].max(),
            ml_config.COL_MODAL_PRICE,
        ]
        latest_price = float(raw_latest_rows.median())
        validated_last = float(ctx["prices"][-1]) if len(ctx["prices"]) else latest_price
        if validated_last > 0 and (
            not np.isfinite(latest_price)
            or latest_price <= 0
            or latest_price / validated_last > 5
            or latest_price / validated_last < 0.2
        ):
            latest_price = validated_last
        sane = sanitize_forecast(fc["low"], fc["median"], fc["high"], ctx["prices"])
        fc["low"], fc["median"], fc["high"] = sane["low"], sane["median"], sane["high"]
        forecast_list = []
        for i in range(ml_config.FORECAST_HORIZON):
            day_date = pd.Timestamp(latest_date) + pd.Timedelta(days=i + 1)
            p50 = round(float(fc["median"][i]), 2)
            p10 = round(float(fc["low"][i]), 2)
            p90 = round(float(fc["high"][i]), 2)
            if not (p10 <= p50 <= p90):
                p10, p50, p90 = sorted([p10, p50, p90])
            forecast_list.append({
                "day": i + 1,
                "date": str(day_date.date()),
                "price": p50,
                "p50": p50,
                "p10": p10,
                "p90": p90,
                "price_low": p10,
                "price_high": p90,
            })

        eval_result = evaluate_model(pipe, ctx["prices"])
        eval_response = None
        if eval_result is not None:
            eval_response = {
                "mae": round(float(eval_result["mae"]), 2),
                "rmse": round(float(eval_result["rmse"]), 2),
                "mape": round(float(eval_result["mape"]), 2),
                "chronos_vs_naive_pct": eval_result.get("chronos_vs_naive_pct", 0),
                "baseline_naive": {
                    "mae": round(float(eval_result["baseline_naive"]["mae"]), 2),
                    "rmse": round(float(eval_result["baseline_naive"]["rmse"]), 2),
                    "mape": round(float(eval_result["baseline_naive"]["mape"]), 2),
                },
                "baseline_ma7": {
                    "mae": round(float(eval_result["baseline_ma7"]["mae"]), 2),
                    "rmse": round(float(eval_result["baseline_ma7"]["rmse"]), 2),
                    "mape": round(float(eval_result["baseline_ma7"]["mape"]), 2),
                },
            }

        sale_window = recommend_sale_window(
            forecast_median=fc["median"],
            forecast_low=fc["low"],
            forecast_high=fc["high"],
            latest_price=latest_price,
            quantity_qtl=quantity_qtl,
            storage_cost_per_day=storage_cost_per_day,
            context_n_obs=ctx["context_length"],
        )
        confidence = _confidence_payload(ctx, latest_date)

        notes = []
        if ctx.get("gap_info"):
            notes.append(ctx["gap_info"])
        if ctx.get("n_winsorized", 0) > 0:
            notes.append(f"{ctx['n_winsorized']} extreme outlier(s) clipped from forecast context only.")
        if ctx["context_length"] < 30:
            notes.append(
                f"Only {ctx['context_length']} observations in the context window — forecast confidence is reduced."
            )
        notes.append(confidence["note"])
        notes.extend(sane.get("notes") or [])
        if sane.get("applied"):
            confidence["label"] = "Low"
            confidence["sanity_adjusted"] = True

        resolved = market_result.get("resolved_market", market)
        response = {
            "success": True,
            "commodity": commodity,
            "state": state,
            "district": district,
            "market": resolved,
            "data_source": _source_label(),
            "historical_records": market_result["record_count"],
            "date_range": {
                "start": str(ctx["dates"].min().date()),
                "end": str(latest_date.date()),
            },
            "latest_price": latest_price,
            "latest_actual_date": str(latest_date.date()),
            "context_length": ctx["context_length"],
            "gap_info": ctx.get("gap_info"),
            "n_winsorized": ctx.get("n_winsorized", 0),
            "outlier_handling": {
                "method": "IQR winsorization on Chronos context only",
                "k": ml_config.OUTLIER_IQR_K,
                "n_clipped": int(ctx.get("n_winsorized", 0)),
            },
            "confidence": confidence,
            "data_note": " ".join(notes),
            "forecast": forecast_list,
            "evaluation": eval_response,
            "sale_window": sale_window,
            "forecast_sanity": {
                "applied": bool(sane.get("applied")),
                "notes": sane.get("notes") or [],
                "historical_anchor": sane.get("anchor"),
            },
            "unit": "INR per quintal",
        }
        if market_result.get("message"):
            response["message"] = market_result["message"]
        return jsonify(response), 200

    @app.route("/api/market-intel", methods=["GET", "POST"])
    def market_intel():
        data = request.get_json(silent=True) or {}
        commodity = (request.args.get("commodity") or data.get("commodity") or "").strip()
        state = (request.args.get("state") or data.get("state") or "").strip()
        district = (request.args.get("district") or data.get("district") or "").strip()
        market = (request.args.get("market") or data.get("market") or "").strip()
        if not all([commodity, state, district, market]):
            return _public_error("Missing required parameter(s).")

        market_result = get_market_data(_df(), commodity, state, district, market)
        if market_result["source"] == "Insufficient data":
            return _public_error(
                market_result.get("message", "No data for this market."),
                422,
                available_markets=market_result.get("available_markets") or [],
            )

        mdf = market_result["data"]
        dates_col = mdf[ml_config.COL_DATE]
        latest_date = dates_col.max()
        latest_price = float(
            mdf.loc[dates_col == latest_date, ml_config.COL_MODAL_PRICE].median()
        )
        ctx = prepare_context(mdf)
        confidence = _confidence_payload(ctx, latest_date)
        return jsonify({
            "success": True,
            "commodity": commodity,
            "state": state,
            "district": district,
            "market": market_result.get("resolved_market", market),
            "historical_records": market_result["record_count"],
            "unique_dates": int(mdf[ml_config.COL_DATE].nunique()),
            "date_range": {
                "start": str(dates_col.min().date()),
                "end": str(latest_date.date()),
            },
            "latest_price": round(latest_price, 2),
            "latest_date": str(latest_date.date()),
            "days_since_last_record": confidence["days_since_last_record"],
            "stale_data": confidence["stale_data"],
            "context_length": ctx["context_length"],
            "gap_info": ctx.get("gap_info"),
            "n_winsorized": ctx.get("n_winsorized", 0),
            "data_confidence": confidence["label"],
            "confidence": confidence,
            "data_source": _source_label(),
        }), 200

    @app.route("/api/market-compare", methods=["GET", "POST"])
    def market_compare():
        data = request.get_json(silent=True) or {}
        commodity = (request.args.get("commodity") or data.get("commodity") or "").strip()
        state = (request.args.get("state") or data.get("state") or "").strip()
        district = (request.args.get("district") or data.get("district") or "").strip()
        if not all([commodity, state, district]):
            return _public_error("Missing required parameter(s).")

        df = _df()
        mask = _mask_commodity_state_district(df, commodity, state, district)
        sub = df[mask]
        if sub.empty:
            return _public_error(
                f"No historical records for {commodity} in {district}, {state}.",
                422,
            )

        markets_list = []
        for mkt_name, grp in sub.groupby(ml_config.COL_MARKET):
            grp_sorted = grp.sort_values(ml_config.COL_DATE)
            n_records = len(grp_sorted)
            n_unique_dates = grp_sorted[ml_config.COL_DATE].nunique()
            latest_date = grp_sorted[ml_config.COL_DATE].max()
            latest_price = float(
                grp_sorted.loc[
                    grp_sorted[ml_config.COL_DATE] == latest_date,
                    ml_config.COL_MODAL_PRICE,
                ].median()
            )
            recent_30 = grp_sorted.tail(30)[ml_config.COL_MODAL_PRICE]
            days_old = int((pd.Timestamp.today().normalize() - pd.Timestamp(latest_date).normalize()).days)
            markets_list.append({
                "market": mkt_name,
                "record_count": int(n_records),
                "unique_dates": int(n_unique_dates),
                "latest_price": round(latest_price, 2),
                "latest_date": str(latest_date.date()),
                "days_since_update": days_old,
                "stale_data": days_old > 7,
                "recent_median": round(float(recent_30.median()), 2),
                "recent_min": round(float(recent_30.min()), 2),
                "recent_max": round(float(recent_30.max()), 2),
                "has_enough_data": int(n_unique_dates) >= ml_config.MIN_RECORDS,
            })
        markets_list.sort(key=lambda x: x["latest_price"], reverse=True)
        return jsonify({
            "success": True,
            "commodity": commodity,
            "state": state,
            "district": district,
            "data_source": _source_label(),
            "markets": markets_list,
            "note": (
                "Prices are the latest modal prices in the historical dataset for each market. "
                "They are not claimed to be today's live quotes."
            ),
        }), 200

    @app.route("/api/sell-now", methods=["POST"])
    def sell_now():
        """Rank markets by net realisation after labelled transport (not raw sticker price)."""
        data = request.get_json(silent=True) or {}
        commodity = (data.get("commodity") or "").strip()
        state = (data.get("state") or "").strip()
        district = (data.get("district") or "").strip()
        origin_market = (data.get("market") or "").strip()
        # `x or 10` would silently turn an explicit 0 into 10, so only a
        # genuinely absent value falls back to the default.
        raw_qty = data.get("quantity_qtl")
        if raw_qty in (None, ""):
            raw_qty = 10
        try:
            quantity_qtl = float(raw_qty)
        except (TypeError, ValueError):
            return _public_error("quantity_qtl must be numeric.")
        if quantity_qtl != quantity_qtl or quantity_qtl in (float("inf"), float("-inf")):
            return _public_error("quantity_qtl must be a finite number.")
        if quantity_qtl <= 0:
            return _public_error("quantity_qtl must be greater than zero.")
        if not commodity or not state or not district:
            return _public_error("commodity, state and district are required.")

        gps_lat, gps_lon, gps_err = _optional_lat_lon(data)
        if gps_err:
            return _public_error(gps_err)

        df = _df()
        if df.empty:
            return _public_error("Mandi dataset is not loaded.", 503)

        mask = df["_commodity_l"] == commodity.lower()
        mask = mask & (df["_state_l"] == state.lower())
        sub = df[mask]
        if sub.empty:
            return _public_error(f"No historical records for {commodity} in {state}.", 422)

        allow_net = _allow_external_http()
        live_feed = fetch_live_prices(commodity=commodity, state=state, limit=200)
        live_by_market = {}
        if live_feed.get("success"):
            for rec in live_feed.get("records") or []:
                live_by_market[(rec.get("market") or "").strip().lower()] = rec

        origin_lat = origin_lon = None
        origin_src = None
        if gps_lat is not None:
            origin_lat, origin_lon = gps_lat, gps_lon
            origin_src = "browser_gps"
        else:
            verified = verified_district_coords(state, district)
            if verified:
                origin_lat, origin_lon, origin_src = verified
            elif allow_net:
                geo = geocode_market("", district, state, allow_network=True)
                if geo.get("success"):
                    origin_lat, origin_lon = geo["lat"], geo["lon"]
                    origin_src = geo.get("source")

        candidates = []
        for mkt_name, grp in sub.groupby(ml_config.COL_MARKET):
            grp_sorted = grp.sort_values(ml_config.COL_DATE)
            latest_date = grp_sorted[ml_config.COL_DATE].max()
            dest_district = str(grp_sorted[ml_config.COL_DISTRICT].mode().iloc[0])
            dest_state = str(grp_sorted[ml_config.COL_STATE].mode().iloc[0])
            prices = grp_sorted.loc[
                grp_sorted[ml_config.COL_DATE] == latest_date,
                ml_config.COL_MODAL_PRICE,
            ].astype(float)
            prices = prices[np.isfinite(prices) & (prices > 0)]
            if prices.empty:
                continue
            latest_price = float(prices.median())
            recent = grp_sorted.tail(30)[ml_config.COL_MODAL_PRICE].astype(float)
            recent = recent[np.isfinite(recent) & (recent > 0)]
            if len(recent) and (
                latest_price / float(recent.median()) > 5
                or latest_price / float(recent.median()) < 0.2
            ):
                latest_price = float(recent.median())
            is_live_price = False
            price_source = "historical mandi dataset"
            live_rec = live_by_market.get(str(mkt_name).strip().lower())
            if live_rec and live_rec.get("modal_price"):
                latest_price = float(live_rec["modal_price"])
                latest_date = live_rec.get("arrival_date") or latest_date
                is_live_price = bool(live_rec.get("is_today"))
                price_source = live_rec.get("source") or "data.gov.in / AGMARKNET"
            days_old, freshness_label = _freshness_fields(latest_date, is_live_price)
            same_mkt = bool(origin_market) and origin_market.lower() == str(mkt_name).lower()
            dist = estimate_distance_km(state, district, dest_state, dest_district, same_market=same_mkt)
            money = net_realisation(latest_price, quantity_qtl, dist["km"])
            freshness_penalty = 0.0
            if days_old > 30:
                freshness_penalty = min(0.15, days_old / 2000.0)
            score = money["net_realisation"] * (1.0 - freshness_penalty)
            candidates.append({
                "market": str(mkt_name),
                "district": dest_district,
                "state": dest_state,
                "latest_price": round(latest_price, 2),
                "modal_price": round(latest_price, 2),
                "latest_date": str(pd.Timestamp(latest_date).date()) if not isinstance(latest_date, str) else str(latest_date)[:10],
                "days_since_update": days_old,
                "stale_data": days_old > 7,
                "is_live_today": is_live_price,
                "is_live_price": is_live_price,
                "freshness_label": freshness_label,
                "price_source": price_source,
                "distance_km": dist["km"],
                "duration_minutes": None,
                "distance_method": dist["method"],
                "distance_source": dist["method"],
                "distance_estimated": True,
                "gross_sale_value": money["gross_sale_value"],
                "gross_value": money["gross_sale_value"],
                "transport_cost": money["transport_cost"],
                "handling_cost": money["handling_cost"],
                "mandi_fee_estimate": money["mandi_fee_estimate"],
                "mandi_fee": money["mandi_fee_estimate"],
                "total_cost": round(
                    money["transport_cost"] + money["handling_cost"] + money["mandi_fee_estimate"], 2
                ),
                "net_realisation": money["net_realisation"],
                "net_per_qtl": round(money["net_realisation"] / quantity_qtl, 2) if quantity_qtl else 0,
                "score": round(score, 2),
                "record_count": int(len(grp_sorted)),
                "unit": "INR per quintal",
                "_same_market": same_mkt,
            })

        if not candidates:
            return _public_error("No usable market prices for this selection.", 422)

        candidates.sort(key=lambda x: x["score"], reverse=True)
        refine = candidates[:15]
        dest_coord_cache = {}
        for row in refine:
            dest_lat = dest_lon = None
            dest_src = None
            cache_key = (row["market"].lower(), row["district"].lower(), row["state"].lower())
            if cache_key in dest_coord_cache:
                dest_lat, dest_lon, dest_src = dest_coord_cache[cache_key]
            else:
                if allow_net:
                    geo = geocode_market(row["market"], row["district"], row["state"], allow_network=True)
                    if geo.get("success"):
                        dest_lat, dest_lon = geo["lat"], geo["lon"]
                        dest_src = geo.get("source")
                if dest_lat is None:
                    verified_dest = verified_district_coords(row["state"], row["district"])
                    if verified_dest:
                        dest_lat, dest_lon, dest_src = verified_dest
                dest_coord_cache[cache_key] = (dest_lat, dest_lon, dest_src)

            if origin_lat is not None and dest_lat is not None:
                routed = compute_route(origin_lat, origin_lon, dest_lat, dest_lon, allow_network=allow_net)
                if routed.get("success"):
                    row["distance_km"] = routed["distance_km"]
                    row["duration_minutes"] = routed.get("duration_minutes")
                    row["distance_source"] = routed.get("source")
                    row["distance_method"] = routed.get("source")
                    row["distance_estimated"] = bool(routed.get("estimated"))
                    row["routing_note"] = routed.get("note")
                    money = net_realisation(row["modal_price"], quantity_qtl, row["distance_km"])
                    row["gross_sale_value"] = money["gross_sale_value"]
                    row["gross_value"] = money["gross_sale_value"]
                    row["transport_cost"] = money["transport_cost"]
                    row["handling_cost"] = money["handling_cost"]
                    row["mandi_fee_estimate"] = money["mandi_fee_estimate"]
                    row["mandi_fee"] = money["mandi_fee_estimate"]
                    row["total_cost"] = round(
                        money["transport_cost"] + money["handling_cost"] + money["mandi_fee_estimate"], 2
                    )
                    row["net_realisation"] = money["net_realisation"]
                    row["net_per_qtl"] = round(money["net_realisation"] / quantity_qtl, 2) if quantity_qtl else 0
                    penalty = 0.0
                    if row["days_since_update"] > 30:
                        penalty = min(0.15, row["days_since_update"] / 2000.0)
                    row["score"] = round(money["net_realisation"] * (1.0 - penalty), 2)
                row["dest_coords_source"] = dest_src
            else:
                row["routing_note"] = (
                    "No verified coordinates for this market — straight-line district estimate."
                )
                row["dest_coords_source"] = dest_src
            row.pop("_same_market", None)

        refine.sort(key=lambda x: x["score"], reverse=True)
        top = refine[:12]
        best = top[0]
        rate = transport_rate()
        loading_rate = transport_loading_rate()
        any_road = any(not m.get("distance_estimated", True) for m in top)
        live_note = None
        if not live_feed.get("configured"):
            live_note = "Live mandi feed unavailable. Showing latest verified mandi data."
        elif not live_feed.get("success"):
            live_note = "Live mandi service unavailable. Showing latest verified mandi data."
        elif not live_feed.get("live"):
            live_note = "Official feed returned no today-dated rows. Showing latest available mandi data."

        explanation = (
            f"Why this market? {best['market']} currently ranks highest on estimated "
            f"net realisation after labelled transport, handling, and mandi fee for "
            f"{quantity_qtl:g} QTL of {commodity}."
        )
        distance_disclaimer = (
            "Road distances from a routing provider."
            if any_road else
            "Road routing unavailable — straight-line distance estimate."
        )
        return jsonify({
            "success": True,
            "commodity": commodity,
            "origin_state": state,
            "origin_district": district,
            "origin_gps_used": gps_lat is not None,
            "origin_coords_source": origin_src,
            "quantity_qtl": quantity_qtl,
            "recommended": best,
            "markets": top,
            "explanation": explanation,
            "data_source": _source_label(),
            "dev_fixture": _dev_fixture_active(),
            "live_feed": {
                "configured": bool(live_feed.get("configured")),
                "success": bool(live_feed.get("success")),
                "live": bool(live_feed.get("live")),
                "error": live_feed.get("error"),
            },
            "live_note": live_note,
            "distance_disclaimer": distance_disclaimer,
            "cost_disclaimer": (
                f"ESTIMATED TRANSPORT COST uses a configurable two-part planning tariff: "
                f"₹{loading_rate:g}/QTL loading plus ₹{rate:g}/QTL/km of distance "
                f"(TRANSPORT_LOADING_PER_QTL, TRANSPORT_RATE_PER_QTL_KM). This is not an "
                f"official universal tariff, invoice, or quoted freight. Handling and the "
                f"~1% mandi fee are also labelled estimates."
            ),
        }), 200

    @app.route("/api/sale-window", methods=["POST"])
    def sale_window():
        data = request.get_json(silent=True) or {}
        commodity = (data.get("commodity") or "").strip()
        state = (data.get("state") or "").strip()
        district = (data.get("district") or "").strip()
        market = (data.get("market") or "").strip()
        try:
            quantity_qtl = float(data.get("quantity_qtl", 10) or 10)
            storage_cost_per_day = float(data.get("storage_cost_per_day", 0) or 0)
        except (TypeError, ValueError):
            return _public_error("quantity_qtl and storage_cost_per_day must be numeric.")
        if not all([commodity, state, district, market]):
            return _public_error("Missing required parameter(s).")
        pipe = _pipeline()
        if pipe is None:
            return _public_error("Forecast model is not loaded.", 503)
        market_result = get_market_data(_df(), commodity, state, district, market)
        if market_result["source"] == "Insufficient data":
            return _public_error(market_result.get("message", "Insufficient data."), 422)
        try:
            ctx = prepare_context(market_result["data"])
            fc = forecast_with_quantiles(pipe, ctx["context_tensor"])
        except Exception:
            return _public_error("Could not compute a sale-window recommendation.", 500)
        raw_latest_date = market_result["data"][ml_config.COL_DATE].max()
        raw_latest_price = market_result["data"].loc[
            market_result["data"][ml_config.COL_DATE] == raw_latest_date,
            ml_config.COL_MODAL_PRICE,
        ]
        latest_price = float(raw_latest_price.median())
        sane = sanitize_forecast(fc["low"], fc["median"], fc["high"], ctx["prices"])
        fc["low"], fc["median"], fc["high"] = sane["low"], sane["median"], sane["high"]
        decision = recommend_sale_window(
            forecast_median=fc["median"],
            forecast_low=fc["low"],
            forecast_high=fc["high"],
            latest_price=latest_price,
            quantity_qtl=quantity_qtl,
            storage_cost_per_day=storage_cost_per_day,
            context_n_obs=ctx["context_length"],
        )
        decision["success"] = True
        decision["commodity"] = commodity
        decision["market"] = market_result.get("resolved_market", market)
        decision["latest_price"] = latest_price
        decision["latest_actual_date"] = str(raw_latest_date.date())
        return jsonify(decision), 200

    @app.route("/api/buyer-demands", methods=["GET"])
    def buyer_demands():
        import re
        commodity = request.args.get("commodity", "").strip().lower()
        store = _store()
        demands = list(store["buyers"])

        def _crop_base(s):
            return re.sub(r"\s*\(.*?\)", "", s or "").lower().strip()

        if commodity:
            demands = [
                d for d in demands
                if commodity in _crop_base(d.get("crop", ""))
                or _crop_base(d.get("crop", "")) in commodity
            ]
        return jsonify({
            "success": True,
            "demands": demands,
            "data_note": store["buyer_note"],
            "count": len(demands),
        }), 200

    @app.route("/api/buyer-match", methods=["POST"])
    def buyer_match():
        data = request.get_json(silent=True) or {}
        commodity = (data.get("commodity") or "").strip()
        state = (data.get("state") or "").strip()
        grade = (data.get("grade") or "Grade A").strip()
        try:
            quantity_qtl = float(data.get("quantity_qtl", 10) or 10)
            expected_price = float(data.get("expected_price", 0) or 0)
        except (TypeError, ValueError):
            return _public_error("quantity_qtl and expected_price must be numeric.")
        if not commodity:
            return _public_error("Missing 'commodity' field.")
        store = _store()
        matches = match_buyers(
            lot_commodity=commodity,
            lot_quantity_qtl=quantity_qtl,
            lot_grade=grade,
            lot_state=state,
            lot_expected_price=expected_price,
            buyer_demands=store["buyers"],
        )
        return jsonify({
            "success": True,
            "commodity": commodity,
            "request_context": {
                "commodity": commodity,
                "state": state,
                "district": (data.get("district") or "").strip(),
                "market": (data.get("market") or "").strip(),
                "quantity_qtl": quantity_qtl,
                "grade": grade,
                "expected_price": expected_price,
            },
            "matches": matches,
            "data_note": store["buyer_note"] + " Scores are weighted fits of price, quantity, grade, location, and trust — not a fixed percentage.",
        }), 200

    @app.route("/api/buyer-matches", methods=["GET"])
    def buyer_matches():
        """Query-form alias for clients that use the plural resource name."""
        params = request.args
        commodity = (params.get("commodity") or "").strip()
        state = (params.get("state") or "").strip()
        grade = (params.get("grade") or "Grade A").strip()
        try:
            quantity_qtl = float(params.get("quantity_qtl", 10) or 10)
            expected_price = float(params.get("expected_price", 0) or 0)
        except (TypeError, ValueError):
            return _public_error("quantity_qtl and expected_price must be numeric.")
        if not commodity:
            return _public_error("Missing 'commodity' parameter.")
        store = _store()
        matches = match_buyers(
            lot_commodity=commodity,
            lot_quantity_qtl=quantity_qtl,
            lot_grade=grade,
            lot_state=state,
            lot_expected_price=expected_price,
            buyer_demands=store["buyers"],
        )
        return jsonify({
            "success": True,
            "commodity": commodity,
            "request_context": {
                "commodity": commodity,
                "state": state,
                "district": (params.get("district") or "").strip(),
                "market": (params.get("market") or "").strip(),
                "quantity_qtl": quantity_qtl,
                "grade": grade,
                "expected_price": expected_price,
            },
            "matches": matches,
            "data_note": store["buyer_note"] + " Scores are weighted fits of price, quantity, grade, location, and trust — not a fixed percentage.",
        }), 200

    @app.route("/api/ingest/status", methods=["GET"])
    def ingest_status():
        meta = _store()["ingestion_meta"]
        df = _df()
        latest = None if df.empty else str(pd.to_datetime(df[ml_config.COL_DATE]).max().date())
        live = official_api_configured()
        synthetic = _dev_fixture_active()
        return jsonify({
            "success": True,
            "total_records": len(df),
            "latest_date_in_dataset": latest or meta.get("latest_date_in_dataset"),
            "last_ingestion_run": meta.get("last_update"),
            "sources": meta.get("sources"),
            "live_api_connected": live,
            "official_api_configured": live,
            "dev_fixture": synthetic,
            "data_source_label": _source_label(),
            "ingest_token_required": bool(ml_config.INGEST_TOKEN),
            "note": (
                dev_fixture.SOURCE_LABEL
                if synthetic else
                "Official data.gov.in fetch is configured."
                if live else
                "No DATA_GOV_API_KEY / DATA_GOV_RESOURCE_ID in the environment. "
                "POST JSON records to /api/ingest/update for daily appends. "
                "Forecasts use historical CSVs plus any ingested rows. "
                "The latest dataset date is not automatically 'today'."
            ),
        }), 200

    @app.route("/api/ingest/update", methods=["POST"])
    def ingest_update():
        if not _ingest_authorized():
            return _public_error("Unauthorized ingest request.", 401)

        data = request.get_json(silent=True) or {}
        source = str(data.get("source") or "json_post")[:80]
        records = data.get("records", [])

        if data.get("fetch_from_source"):
            fetched = fetch_official_records()
            if not fetched.get("success"):
                return _public_error(
                    fetched.get("error") or "Official source fetch is unavailable.",
                    503,
                    official_api_configured=fetched.get("configured", False),
                )
            records = fetched["records"]
            source = "data.gov.in"

        if not records:
            return _public_error("No records provided.")
        if not isinstance(records, list):
            return _public_error("'records' must be a list.")

        store = _store()
        persist = not current_app.config.get("TESTING", False)
        with _STORE_LOCK:
            result = ingest_records(records, store["df"], source=source, persist=persist)
            if not result.get("success"):
                return _public_error(result.get("error", "Ingest failed."), 400)
            from ml.data_loader import _add_filter_columns
            store["df"] = _add_filter_columns(result["frame"])
            from datetime import datetime, timezone
            store["ingestion_meta"]["last_update"] = datetime.now(timezone.utc).isoformat()
            store["ingestion_meta"]["total_records"] = result["new_total"]
            store["ingestion_meta"]["latest_date_in_dataset"] = result["latest_date_in_dataset"]

        return jsonify({
            "success": True,
            "inserted": result["inserted"],
            "added": result["added"],
            "skipped": result["skipped"],
            "duplicates_skipped": result["duplicates_skipped"],
            "rejected": result["rejected"],
            "invalid_skipped": result["invalid_skipped"],
            "reject_reasons": result.get("reject_reasons") or {},
            "new_total": result["new_total"],
            "latest_date_in_dataset": result["latest_date_in_dataset"],
            "message": f"Ingested {result['inserted']} new records.",
        }), 200

    @app.errorhandler(413)
    def too_large(_e):
        return _public_error("Payload too large.", 413)


    # =========================================================================
    # AUTH ROUTES  /api/auth/...
    # =========================================================================

    @app.route("/api/auth/register", methods=["POST"])
    def auth_register():
        """Register a new user (farmer or buyer).  Returns a signed JWT."""
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        username = (data.get("username") or "").strip()
        phone = (data.get("phone") or "").strip() or None  # optional
        password = (data.get("password") or "").strip()
        role = (data.get("role") or "FARMER").strip().upper()
        email = (data.get("email") or "").strip() or None
        language = (data.get("language") or "en").strip()

        missing = [f for f, v in [("name", name), ("username", username), ("password", password)] if not v]
        if missing:
            return _public_error(f"Missing required field(s): {', '.join(missing)}")
        if role not in ("FARMER", "FPO", "BUYER", "ADMIN"):
            return _public_error("role must be FARMER, FPO, BUYER, or ADMIN.")
        if len(password) < 4:
            return _public_error("Password must be at least 4 characters.")

        try:
            user_id = _user_repo.create_user(
                name=name, username=username, password=password,
                role=role, phone=phone, email=email, language=language,
            )
        except ValueError as exc:
            return _public_error(str(exc), 409)
        except Exception as exc:
            print(f"[DB] register error: {exc}")
            return _public_error("Could not create account. Database may be unavailable.", 500)

        # Create role-specific profile with any extra fields supplied.
        try:
            if role in ("FARMER", "FPO"):
                _user_repo.upsert_farmer_profile(user_id, {
                    "village": data.get("village"),
                    "district": data.get("district"),
                    "state": data.get("state", "Maharashtra"),
                    "pincode": data.get("pincode"),
                    "land_size_acres": data.get("land_size_acres"),
                    "primary_crops": data.get("primary_crops"),
                })
            elif role == "BUYER":
                _user_repo.upsert_buyer_profile(user_id, {
                    "business_name": data.get("business_name") or name,
                    "buyer_type": (data.get("buyer_type") or "TRADER").upper(),
                    "district": data.get("district"),
                    "state": data.get("state", "Maharashtra"),
                })
        except Exception as exc:
            print(f"[DB] profile creation warning: {exc}")

        token = _auth.create_token(user_id, role)
        user = _user_repo.find_user_by_id(user_id)
        return jsonify({
            "success": True,
            "message": "Account created. You are now signed in.",
            "token": token,
            "token_type": "Bearer",
            "user": _user_repo.safe_user_dict(user),
        }), 201


    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        """Authenticate with username + password.  Returns a signed JWT."""
        data = request.get_json(silent=True) or {}
        username = (data.get("username") or "").strip().lower()
        password = (data.get("password") or "").strip()
        if not username or not password:
            return _public_error("Missing 'username' or 'password'.")

        try:
            user = _user_repo.find_user_by_username(username)
        except Exception as exc:
            print(f"[DB] login error: {exc}")
            return _public_error("Database unavailable. Try again shortly.", 503)

        if not user or not _auth.verify_password(password, user.get("password_hash", "")):
            return _public_error("Incorrect username or password.", 401)
        if not user.get("is_active", 1):
            return _public_error("This account has been deactivated.", 401)

        token = _auth.create_token(user["id"], user["role"])
        return jsonify({
            "success": True,
            "message": "Signed in.",
            "token": token,
            "token_type": "Bearer",
            "user": _user_repo.safe_user_dict(user),
        }), 200


    @app.route("/api/auth/me", methods=["GET"])
    @_auth.login_required
    def auth_me():
        """Return the currently authenticated user's account + profile."""
        user_id = _auth.get_current_user_id()
        role = _auth.get_current_role()
        try:
            user = _user_repo.find_user_by_id(user_id)
            if not user:
                return _public_error("User not found.", 404)
            profile = None
            if role in ("FARMER", "FPO"):
                profile = _user_repo.get_farmer_profile(user_id)
            elif role == "BUYER":
                profile = _user_repo.get_buyer_profile(user_id)
            return jsonify({
                "success": True,
                "user": _user_repo.safe_user_dict(user),
                "profile": profile,
                "role": role,
            }), 200
        except Exception as exc:
            print(f"[DB] /api/auth/me error: {exc}")
            return _public_error("Database unavailable.", 503)


    @app.route("/api/auth/me", methods=["PUT"])
    @_auth.login_required
    def auth_update_me():
        """Update name, language, email, or district on the current user."""
        user_id = _auth.get_current_user_id()
        data = request.get_json(silent=True) or {}
        allowed = {"name", "email", "language"}
        updates = {k: v for k, v in data.items() if k in allowed and v}
        try:
            if updates:
                _user_repo.update_user(user_id, updates)
            user = _user_repo.find_user_by_id(user_id)
            return jsonify({"success": True, "user": _user_repo.safe_user_dict(user)}), 200
        except Exception as exc:
            return _public_error(str(exc), 400)


    @app.route("/api/profile/farmer", methods=["PUT"])
    @_auth.login_required
    def update_farmer_profile():
        """Update or create the farmer profile for the current user."""
        user_id = _auth.get_current_user_id()
        data = request.get_json(silent=True) or {}
        try:
            profile = _user_repo.upsert_farmer_profile(user_id, data)
            return jsonify({"success": True, "profile": profile}), 200
        except Exception as exc:
            return _public_error(str(exc), 400)


    @app.route("/api/profile/buyer", methods=["PUT"])
    @_auth.login_required
    def update_buyer_profile():
        """Update or create the buyer profile for the current user."""
        user_id = _auth.get_current_user_id()
        data = request.get_json(silent=True) or {}
        try:
            profile = _user_repo.upsert_buyer_profile(user_id, data)
            return jsonify({"success": True, "profile": profile}), 200
        except Exception as exc:
            return _public_error(str(exc), 400)


    # =========================================================================
    # LOTS ROUTES  /api/lots/...
    # =========================================================================

    @app.route("/api/lots", methods=["GET"])
    def list_lots():
        """Return AVAILABLE lots.  Optionally filter by ?commodity=X."""
        commodity = request.args.get("commodity", "").strip() or None
        try:
            lots = _lot_repo.get_available_lots(commodity=commodity)
            return jsonify({"success": True, "lots": lots, "count": len(lots)}), 200
        except Exception as exc:
            print(f"[DB] list_lots error: {exc}")
            return jsonify({"success": True, "lots": [], "count": 0, "note": "Database unavailable."}), 200


    @app.route("/api/lots", methods=["POST"])
    @_auth.login_required
    def create_lot():
        """Create a new sale lot for the authenticated farmer/FPO."""
        user_id = _auth.get_current_user_id()
        role = _auth.get_current_role()
        if role not in ("FARMER", "FPO", "ADMIN"):
            return _public_error("Only farmers and FPOs can create lots.", 403)
        data = request.get_json(silent=True) or {}
        commodity = (data.get("commodity") or "").strip()
        if not commodity:
            return _public_error("'commodity' is required.")
        try:
            qty = float(data.get("quantity_qtl", 0) or 0)
        except (TypeError, ValueError):
            return _public_error("'quantity_qtl' must be a number.")
        if qty <= 0:
            return _public_error("'quantity_qtl' must be greater than zero.")
        payload = dict(data)
        if payload.get("expected_price") in (None, "", 0):
            for alt in ("price_per_qtl", "expectedPrice", "price"):
                if payload.get(alt) not in (None, ""):
                    payload["expected_price"] = payload.get(alt)
                    break
        location = str(payload.get("location") or "")
        if not payload.get("district") and location:
            payload["district"] = location.split(",")[0].strip()
        try:
            lot_id = _lot_repo.create_lot(user_id, payload)
            lot = _lot_repo.get_lot_by_id(lot_id)
            return jsonify({"success": True, "lot": lot, "message": "Sale lot created."}), 201
        except Exception as exc:
            print(f"[DB] create_lot error: {exc}")
            return _public_error("Could not save lot. Database may be unavailable.", 500)


    @app.route("/api/lots/my", methods=["GET"])
    @_auth.login_required
    def my_lots():
        """Return all lots for the currently authenticated farmer."""
        user_id = _auth.get_current_user_id()
        try:
            lots = _lot_repo.get_lots_by_farmer(user_id)
            return jsonify({"success": True, "lots": lots, "count": len(lots)}), 200
        except Exception as exc:
            print(f"[DB] my_lots error: {exc}")
            return jsonify({"success": True, "lots": [], "count": 0, "note": "Database unavailable."}), 200


    @app.route("/api/lots/<int:lot_id>", methods=["GET"])
    def get_lot(lot_id):
        """Return a single lot by id."""
        try:
            lot = _lot_repo.get_lot_by_id(lot_id)
            if not lot:
                return _public_error("Lot not found.", 404)
            return jsonify({"success": True, "lot": lot}), 200
        except Exception as exc:
            return _public_error("Database unavailable.", 503)


    # =========================================================================
    # BUYER REQUIREMENTS  /api/buyer-requirements/...
    # =========================================================================

    @app.route("/api/buyer-requirements", methods=["GET"])
    def list_buyer_requirements():
        """Return open buyer requirements.  Optionally filter by ?commodity=X."""
        commodity = request.args.get("commodity", "").strip() or None
        try:
            reqs = _lot_repo.get_open_requirements(commodity=commodity)
            return jsonify({"success": True, "requirements": reqs, "count": len(reqs)}), 200
        except Exception as exc:
            print(f"[DB] list_buyer_requirements error: {exc}")
            return jsonify({"success": True, "requirements": [], "count": 0}), 200


    @app.route("/api/buyer-requirements", methods=["POST"])
    @_auth.login_required
    def create_buyer_requirement():
        """Buyer posts a new crop demand."""
        user_id = _auth.get_current_user_id()
        role = _auth.get_current_role()
        if role not in ("BUYER", "ADMIN"):
            return _public_error("Only buyers can post requirements.", 403)
        data = request.get_json(silent=True) or {}
        commodity = (data.get("commodity") or data.get("crop") or "").strip()
        if not commodity:
            return _public_error("'commodity' is required.")
        payload = dict(data)
        payload["commodity"] = commodity
        if payload.get("quantity_qtl_min") in (None, ""):
            q = payload.get("quantity") or payload.get("quantity_qtl")
            if q not in (None, ""):
                payload["quantity_qtl_min"] = q
        if payload.get("price_per_qtl") in (None, ""):
            payload["price_per_qtl"] = payload.get("offeredRate") or payload.get("offered_rate")
        loc = str(payload.get("deliveryLocation") or payload.get("delivery_location") or "")
        if loc and not payload.get("preferred_district"):
            payload["preferred_district"] = loc.split(",")[0].strip()
        try:
            req_id = _lot_repo.create_buyer_requirement(user_id, payload)
            return jsonify({"success": True, "requirement_id": req_id, "message": "Requirement posted."}), 201
        except Exception as exc:
            print(f"[DB] create_buyer_requirement error: {exc}")
            return _public_error("Could not save requirement.", 500)


    @app.route("/api/buyer-requirements/my", methods=["GET"])
    @_auth.login_required
    def my_buyer_requirements():
        """Return all requirements posted by the authenticated buyer."""
        user_id = _auth.get_current_user_id()
        try:
            reqs = _lot_repo.get_requirements_by_buyer(user_id)
            return jsonify({"success": True, "requirements": reqs, "count": len(reqs)}), 200
        except Exception as exc:
            return jsonify({"success": True, "requirements": [], "count": 0}), 200


    # =========================================================================
    # OFFERS  /api/offers/...
    # =========================================================================

    @app.route("/api/offers", methods=["POST"])
    @_auth.login_required
    def create_offer():
        """
        Create an offer.

        Two directions, both persisted in the same `offers` table and told
        apart by `initiated_by`:
          BUYER  -> offers on a farmer's lot          (needs lot_id)
          FARMER -> offers a lot against a buyer's
                    open requirement                  (needs lot_id + requirement_id)
        """
        user_id = _auth.get_current_user_id()
        role = _auth.get_current_role()
        data = request.get_json(silent=True) or {}

        if role == "FARMER":
            return _create_farmer_offer(user_id, data)
        if role not in ("BUYER", "ADMIN"):
            return _public_error("Only buyers and farmers can make offers.", 403)
        lot_id = data.get("lot_id")
        if not lot_id:
            return _public_error("'lot_id' is required.")
        try:
            lot_id = int(lot_id)
            lot = _lot_repo.get_lot_by_id(lot_id)
        except Exception:
            return _public_error("Invalid 'lot_id'.")
        if not lot:
            return _public_error("Lot not found.", 404)
        try:
            price = float(data.get("price_per_qtl", 0) or 0)
            qty = float(data.get("quantity_qtl", lot.get("quantity_qtl", 0)) or 0)
        except (TypeError, ValueError):
            return _public_error("'price_per_qtl' and 'quantity_qtl' must be numbers.")
        if price <= 0:
            return _public_error("'price_per_qtl' must be greater than zero.")
        try:
            offer_id = _lot_repo.create_offer(
                buyer_user_id=user_id,
                seller_user_id=lot["farmer_user_id"],
                lot_id=lot_id,
                data={**data, "price_per_qtl": price, "quantity_qtl": qty},
            )
            return jsonify({"success": True, "offer_id": offer_id, "message": "Offer sent."}), 201
        except Exception as exc:
            print(f"[DB] create_offer error: {exc}")
            return _public_error("Could not save offer.", 500)


    @app.route("/api/offers/my", methods=["GET"])
    @_auth.login_required
    def my_offers():
        """Farmer sees offers on their lots; buyer sees their own outgoing offers."""
        user_id = _auth.get_current_user_id()
        role = _auth.get_current_role()
        try:
            if role in ("FARMER", "FPO"):
                offers = _lot_repo.get_offers_for_seller(user_id)
            else:
                offers = _lot_repo.get_offers_by_buyer(user_id)
            return jsonify({"success": True, "offers": offers, "count": len(offers)}), 200
        except Exception:
            return jsonify({"success": True, "offers": [], "count": 0}), 200


    @app.route("/api/offers/<int:offer_id>/respond", methods=["POST"])
    @_auth.login_required
    def respond_offer(offer_id):
        """Farmer accepts or rejects a buyer's offer."""
        data = request.get_json(silent=True) or {}
        status = (data.get("status") or "").strip().upper()
        if status not in ("ACCEPTED", "REJECTED", "COUNTERED"):
            return _public_error("'status' must be ACCEPTED, REJECTED, or COUNTERED.")
        try:
            _lot_repo.respond_to_offer(offer_id, status)
            result = {"success": True, "offer_id": offer_id, "status": status}
            if status == "ACCEPTED":
                tx = _lot_repo.create_transaction_from_offer(offer_id)
                if tx:
                    result["transaction"] = tx
                    result["message"] = "Offer accepted. Transaction created."
            return jsonify(result), 200
        except Exception as exc:
            print(f"[DB] respond_offer error: {exc}")
            return _public_error("Could not process offer response.", 500)


    # =========================================================================
    # TRANSACTIONS  /api/transactions/...
    # =========================================================================

    @app.route("/api/transactions/my", methods=["GET"])
    @_auth.login_required
    def my_transactions():
        """Return all transactions involving the authenticated user."""
        user_id = _auth.get_current_user_id()
        try:
            txs = _lot_repo.get_transactions_for_user(user_id)
            return jsonify({"success": True, "transactions": txs, "count": len(txs)}), 200
        except Exception:
            return jsonify({"success": True, "transactions": [], "count": 0}), 200

    # =========================================================================
    # FARMER SUPER-APP ROUTES
    # Weather / Schemes / Knowledge / Learning / Helplines / Seeds / Market-Prices
    # =========================================================================

    @app.route("/api/weather", methods=["GET"])
    def get_weather():
        """
        Return weather for a given location using Open-Meteo (free, no API key).
        Accepts: lat/lon OR district+state (we geocode via Open-Meteo geocoding).
        Falls back gracefully if network is unavailable.
        """
        import urllib.request
        import urllib.parse
        import json as _json

        lat = request.args.get("lat", type=float)
        lon = request.args.get("lon", type=float)
        district = request.args.get("district", "").strip()
        state = request.args.get("state", "").strip()
        precision = "unknown"

        if lat is not None and lon is not None:
            _, _, coord_err = validate_coords(lat, lon)
            if coord_err:
                return _public_error(coord_err, 400)
            precision = "browser_gps"
        elif district or state:
            precision = "district_geocode"
            try:
                query = f"{district}, {state}, India".strip(", ")
                geo_url = (
                    "https://geocoding-api.open-meteo.com/v1/search?"
                    + urllib.parse.urlencode({"name": query, "count": 1, "language": "en", "format": "json"})
                )
                with urllib.request.urlopen(geo_url, timeout=5) as resp:
                    geo = _json.loads(resp.read())
                results = geo.get("results", [])
                if results:
                    lat = results[0]["latitude"]
                    lon = results[0]["longitude"]
                else:
                    return _public_error(
                        "Could not geocode that district/state. Check the spelling or provide GPS coordinates.",
                        422,
                    )
            except Exception:
                return jsonify({
                    "success": False,
                    "error": "Weather geocoding unavailable. Enter district and state, or use GPS.",
                }), 503
        else:
            return _public_error(
                "Provide lat and lon, or district and state. Weather is not guessed from a default city.",
                400,
            )

        try:
            wx_url = (
                "https://api.open-meteo.com/v1/forecast?"
                + urllib.parse.urlencode({
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,precipitation",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
                    "timezone": "Asia/Kolkata",
                    "forecast_days": 5,
                })
            )
            with urllib.request.urlopen(wx_url, timeout=8) as resp:
                wx = _json.loads(resp.read())

            current = wx.get("current", {})
            daily = wx.get("daily", {})

            def wx_description(code):
                """Map WMO weather code to human-readable description."""
                c = int(code) if code is not None else 0
                if c == 0: return "Clear sky"
                if c == 1: return "Mainly clear"
                if c == 2: return "Partly cloudy"
                if c == 3: return "Overcast"
                if c in (45, 48): return "Foggy"
                if c in (51, 53, 55): return "Drizzle"
                if c in (61, 63, 65): return "Rain"
                if c in (71, 73, 75): return "Snow"
                if c in (80, 81, 82): return "Rain showers"
                if c in (95, 96, 99): return "Thunderstorm"
                return "Cloudy"

            def farmer_tip(code, rain_prob, temp_max):
                """Simple non-prescriptive weather interpretation for farmers."""
                tips = []
                code = int(code) if code is not None else 0
                rain_prob = rain_prob or 0
                if rain_prob >= 60:
                    tips.append("Rain likely in the coming days — check irrigation and drainage plans.")
                if code in (95, 96, 99):
                    tips.append("Thunderstorm possible — avoid field operations if lightning risk.")
                if temp_max and temp_max >= 40:
                    tips.append("High temperature expected — consider early morning field work.")
                if not tips:
                    tips.append("Weather appears favourable for regular farm activities.")
                return " ".join(tips)

            max_rain_prob = 0
            if daily.get("precipitation_probability_max"):
                probs = [p for p in daily["precipitation_probability_max"] if p is not None]
                max_rain_prob = max(probs) if probs else 0

            max_temp = None
            if daily.get("temperature_2m_max"):
                temps = [t for t in daily["temperature_2m_max"] if t is not None]
                max_temp = max(temps) if temps else None

            forecast_days = []
            dates = daily.get("time", [])
            for i, d in enumerate(dates):
                forecast_days.append({
                    "date": d,
                    "weather_code": daily["weather_code"][i] if daily.get("weather_code") else None,
                    "condition": wx_description(daily["weather_code"][i] if daily.get("weather_code") else 0),
                    "temp_max": daily["temperature_2m_max"][i] if daily.get("temperature_2m_max") else None,
                    "temp_min": daily["temperature_2m_min"][i] if daily.get("temperature_2m_min") else None,
                    "precipitation_mm": daily["precipitation_sum"][i] if daily.get("precipitation_sum") else None,
                    "rain_probability_pct": daily["precipitation_probability_max"][i] if daily.get("precipitation_probability_max") else None,
                })

            return jsonify({
                "success": True,
                "location": {
                    "lat": lat,
                    "lon": lon,
                    "district": district,
                    "state": state,
                    "precision": precision,
                },
                "location_note": (
                    "Using browser GPS coordinates."
                    if precision == "browser_gps" else
                    "District/state-level location (not hyperlocal farm GPS)."
                ),
                "current": {
                    "temperature_c": current.get("temperature_2m"),
                    "humidity_pct": current.get("relative_humidity_2m"),
                    "wind_kmh": current.get("wind_speed_10m"),
                    "precipitation_mm": current.get("precipitation"),
                    "weather_code": current.get("weather_code"),
                    "condition": wx_description(current.get("weather_code", 0)),
                },
                "forecast": forecast_days,
                "farmer_tip": farmer_tip(current.get("weather_code", 0), max_rain_prob, max_temp),
                "source": "Open-Meteo (open-meteo.com) — Free, no API key required",
                "updated": current.get("time", ""),
                "unit_note": "Temperature in °C, wind in km/h, precipitation in mm",
            }), 200

        except Exception as exc:
            # Log the cause server-side; never hand raw exception text (which can
            # carry internal paths or library details) to the browser.
            print(f"[weather] upstream failed: {exc}")
            return jsonify({
                "success": False,
                "error": (
                    "Weather is unavailable because this server has outbound "
                    "internet disabled."
                    if not _allow_external_http() else
                    "Weather data temporarily unavailable. Please try again."
                ),
                "location": {"lat": lat, "lon": lon, "district": district, "state": state},
            }), 503

    @app.route("/api/schemes", methods=["GET"])
    def get_schemes():
        """Return curated government schemes data from backend/data/schemes.json."""
        import json as _json
        data_file = os.path.join(_BACKEND_DIR, "data", "schemes.json")
        try:
            with open(data_file, encoding="utf-8") as f:
                schemes = _json.load(f)
            category = request.args.get("category", "").strip().lower()
            scope = request.args.get("scope", "").strip().lower()
            if category:
                schemes = [s for s in schemes if category in s.get("category", "").lower()]
            if scope:
                schemes = [s for s in schemes if scope in s.get("scope", "").lower()]
            return jsonify({"success": True, "schemes": schemes, "count": len(schemes),
                            "source": "Ministry of Agriculture & Farmers Welfare, Government of India",
                            "note": "Information is curated for awareness. Verify eligibility and amounts on official portals before applying."}), 200
        except Exception as exc:
            print(f"[schemes] {exc}")
            return jsonify({"success": False, "error": "Schemes data unavailable."}), 500

    @app.route("/api/knowledge", methods=["GET"])
    def get_knowledge():
        """Return farming knowledge cards from backend/data/knowledge.json."""
        import json as _json
        data_file = os.path.join(_BACKEND_DIR, "data", "knowledge.json")
        try:
            with open(data_file, encoding="utf-8") as f:
                items = _json.load(f)
            category = request.args.get("category", "").strip().lower()
            q = request.args.get("q", "").strip().lower()
            if category:
                items = [k for k in items if category in k.get("category", "").lower()]
            if q:
                items = [k for k in items if q in k.get("title", "").lower() or q in k.get("summary", "").lower()]
            return jsonify({"success": True, "knowledge": items, "count": len(items)}), 200
        except Exception as exc:
            print(f"[knowledge] {exc}")
            return jsonify({"success": False, "error": "Knowledge data unavailable."}), 500

    @app.route("/api/learning", methods=["GET"])
    def get_learning():
        """Return curated educational resources from backend/data/learning.json."""
        import json as _json
        data_file = os.path.join(_BACKEND_DIR, "data", "learning.json")
        try:
            with open(data_file, encoding="utf-8") as f:
                items = _json.load(f)
            topic = request.args.get("topic", "").strip().lower()
            if topic:
                items = [r for r in items if topic in r.get("topic", "").lower() or topic in r.get("title", "").lower()]
            return jsonify({"success": True, "resources": items, "count": len(items)}), 200
        except Exception as exc:
            print(f"[learning] {exc}")
            return jsonify({"success": False, "error": "Learning resources unavailable."}), 500

    @app.route("/api/helplines", methods=["GET"])
    def get_helplines():
        """Return verified official helpline numbers from backend/data/helplines.json."""
        import json as _json
        data_file = os.path.join(_BACKEND_DIR, "data", "helplines.json")
        try:
            with open(data_file, encoding="utf-8") as f:
                items = _json.load(f)
            category = request.args.get("category", "").strip().lower()
            if category:
                items = [h for h in items if category in h.get("category", "").lower()]
            return jsonify({"success": True, "helplines": items, "count": len(items),
                            "note": "All numbers are official government/PSU helplines. Verify availability before calling."}), 200
        except Exception as exc:
            print(f"[helpline] {exc}")
            return jsonify({"success": False, "error": "Helpline data unavailable."}), 500

    @app.route("/api/seeds", methods=["GET"])
    def get_seeds():
        """Return official seed organization info from backend/data/seeds.json."""
        import json as _json
        data_file = os.path.join(_BACKEND_DIR, "data", "seeds.json")
        try:
            with open(data_file, encoding="utf-8") as f:
                items = _json.load(f)
            return jsonify({"success": True, "organizations": items, "count": len(items),
                            "note": "This section provides information about official seed sources. KisanLink does not sell seeds."}), 200
        except Exception as exc:
            print(f"[seeds] {exc}")
            return jsonify({"success": False, "error": "Seeds data unavailable."}), 500

    @app.route("/api/market-prices/latest", methods=["GET"])
    def get_latest_market_prices():
        """
        Return latest available mandi prices from the real historical dataset.
        Accepts: commodity (required), state (optional), district (optional), market (optional).
        Returns top N records sorted by date descending.
        NEVER labels old data as today's price — always shows the actual data date.
        """
        commodity = request.args.get("commodity", "").strip()
        state     = request.args.get("state", "").strip()
        district  = request.args.get("district", "").strip()
        market    = request.args.get("market", "").strip()
        limit     = min(int(request.args.get("limit", 50)), 200)

        if not commodity:
            return _public_error("commodity parameter is required", 400)

        try:
            df = _df()
            if df.empty:
                return jsonify({"success": True, "prices": [], "count": 0,
                                "message": "Dataset not loaded.", "latest_date": None}), 200

            mask = df["_commodity_l"] == commodity.strip().lower()
            if state:
                mask &= df["_state_l"] == state.strip().lower()
            if district:
                mask &= df["_district_l"] == district.strip().lower()
            if market:
                if "_market_l" in df.columns:
                    mask &= df["_market_l"] == market.strip().lower()
                else:
                    mask &= df[ml_config.COL_MARKET].astype(str).str.lower() == market.strip().lower()

            sub = df[mask]
            if sub.empty:
                return jsonify({"success": True, "prices": [], "count": 0,
                                "message": f"No records found for {commodity}.",
                                "latest_date": None}), 200

            date_col = ml_config.COL_DATE if ml_config.COL_DATE in sub.columns else None
            if date_col is None:
                for c in ("arrival_date", "Arrival_Date", "date", "Date"):
                    if c in sub.columns:
                        date_col = c
                        break

            if date_col:
                sub = sub.sort_values(date_col, ascending=False)
                latest_date = str(sub[date_col].iloc[0])[:10] if len(sub) > 0 else None
            else:
                latest_date = None

            synthetic = _dev_fixture_active()
            row_source = (
                "Synthetic development fixture"
                if synthetic else
                "Historical mandi CSVs (government open data)"
            )

            # Build output rows
            records = []
            seen = set()
            for _, row in sub.iterrows():
                mkt_key = str(row.get("Market", row.get("market", ""))).strip()
                dist_key = str(row.get("District", row.get("district", ""))).strip()
                key = (mkt_key, dist_key)
                if key in seen:
                    continue
                seen.add(key)
                def _price(*names):
                    for n in names:
                        if n in row.index and pd.notna(row[n]):
                            try:
                                val = float(row[n])
                            except (TypeError, ValueError):
                                continue
                            if np.isfinite(val) and val > 0:
                                return round(val, 2)
                    return None

                def _text(*names):
                    for n in names:
                        if n in row.index and pd.notna(row[n]):
                            val = str(row[n]).strip()
                            if val and val.lower() not in {"nan", "none", "null"}:
                                return val
                    return ""

                records.append({
                    "commodity": str(row.get(ml_config.COL_COMMODITY, commodity)).strip(),
                    "variety": _text(ml_config.COL_VARIETY, "variety", "Variety"),
                    "grade": _text(ml_config.COL_GRADE, "grade", "Grade"),
                    "market": mkt_key,
                    "district": dist_key,
                    "state": str(row.get(ml_config.COL_STATE, state)).strip(),
                    "min_price": _price(ml_config.COL_MIN_PRICE, "min_price", "Min_Price"),
                    "max_price": _price(ml_config.COL_MAX_PRICE, "max_price", "Max_Price"),
                    "modal_price": _price(ml_config.COL_MODAL_PRICE, "modal_price", "Modal_Price"),
                    "date": str(row[date_col])[:10] if date_col else None,
                    "unit": "₹/Quintal",
                    "source": row_source,
                    "is_live": False,
                })
                if len(records) >= limit:
                    break

            import datetime
            today_str = datetime.date.today().isoformat()
            data_is_current = (latest_date == today_str) if latest_date else False
            if synthetic:
                # Synthetic rows are never described as today's real mandi data.
                label = "Sample data (synthetic development fixture)"
                data_is_current = False
                note = (
                    "These are generated sample rows for development and demo "
                    "only. They are not real mandi prices."
                )
            elif data_is_current:
                label = "Today's mandi data"
                note = f"Showing most recent available records. Dataset latest date: {latest_date or 'unknown'}."
            else:
                label = "Latest available mandi data"
                note = f"Showing most recent available records. Dataset latest date: {latest_date or 'unknown'}."

            return jsonify({
                "success": True,
                "prices": records,
                "count": len(records),
                "latest_date": latest_date,
                "label": label,
                "is_live_today": data_is_current,
                "is_live": False,
                "dev_fixture": synthetic,
                "source": (
                    dev_fixture.SOURCE_LABEL
                    if synthetic else
                    "Combined historical mandi CSVs (government open data). Not a live API feed."
                ),
                "note": note,
            }), 200

        except Exception as exc:
            return _public_error(f"Market prices lookup failed: {str(exc)[:300]}", 500)

    @app.route("/api/market-prices/live", methods=["GET"])
    def get_live_market_prices():
        commodity = request.args.get("commodity", "").strip()
        state = request.args.get("state", "").strip()
        district = request.args.get("district", "").strip()
        market = request.args.get("market", "").strip()
        try:
            limit = min(int(request.args.get("limit", 100)), 500)
        except (TypeError, ValueError):
            limit = 100
        payload = fetch_live_prices(
            commodity=commodity, state=state, district=district, market=market, limit=limit,
        )
        payload["is_live"] = bool(payload.get("live"))
        if not payload.get("success"):
            payload["label"] = "Live mandi feed unavailable"
        return jsonify(payload), 200

    @app.route("/api/location/reverse", methods=["GET"])
    def location_reverse():
        lat = request.args.get("lat")
        lon = request.args.get("lon")
        lat_f, lon_f, err = validate_coords(lat, lon)
        if err:
            return _public_error(err, 400)
        result = reverse_geocode(lat_f, lon_f, allow_network=_allow_external_http())
        if not result.get("success"):
            return jsonify({
                "success": False,
                "error": result.get("error") or "Reverse geocoding unavailable.",
                "lat": lat_f,
                "lon": lon_f,
            }), 503
        return jsonify(result), 200

    @app.route("/api/route", methods=["POST"])
    def api_route():
        data = request.get_json(silent=True) or {}
        origin = data.get("origin") or {}
        destination = data.get("destination") or {}
        o_lat, o_lon, err = validate_coords(origin.get("lat"), origin.get("lon"))
        if err:
            return _public_error(f"Invalid origin: {err}", 400)
        d_lat, d_lon, err = validate_coords(destination.get("lat"), destination.get("lon"))
        if err:
            return _public_error(f"Invalid destination: {err}", 400)
        routed = compute_route(o_lat, o_lon, d_lat, d_lon, allow_network=_allow_external_http())
        if not routed.get("success"):
            return jsonify({
                "success": False,
                "error": routed.get("error") or "Routing failed.",
                "estimated": True,
            }), 503
        return jsonify({
            "success": True,
            "distance_km": routed["distance_km"],
            "duration_minutes": routed.get("duration_minutes"),
            "source": routed.get("source"),
            "estimated": bool(routed.get("estimated")),
            "note": routed.get("note"),
        }), 200


def get_app():
    global _REAL_APP
    if _REAL_APP is None:
        with _INIT_LOCK:
            if _REAL_APP is None:
                skip = os.environ.get("KISANLINK_SKIP_STARTUP", "").lower() in {"1", "true", "yes"}
                _REAL_APP = create_app(load_real_data=not skip, load_chronos=not skip)
    return _REAL_APP


class _LazyApp:
    """Defer CSV/Chronos load until the first WSGI request or get_app()."""

    def __call__(self, environ, start_response):
        return get_app()(environ, start_response)

    def __getattr__(self, name):
        return getattr(get_app(), name)


app = _LazyApp()


if __name__ == "__main__":
    application = create_app()
    print("[KisanLink API] Starting server on http://localhost:5000")
    print("[KisanLink API] Frontend: http://localhost:5000/pages/farmer.html")
    application.run(host="127.0.0.1", port=5000, debug=False)
