"""
KisanLink Backend — ML Forecast API Server
============================================
Flask API for Chronos forecasting, market intel, buyer matching, and ingestion.

Historical prices come from the combined mandi CSVs plus persisted ingested rows.
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

from ml.data_loader import load_combined_data, get_market_data, prepare_context
from ml.forecaster import load_model, forecast_with_quantiles
from ml.evaluator import evaluate_model
from ml.decision_engine import recommend_sale_window
from ml.buyer_matcher import match_buyers
from ml.ingest import (
    ingest_records,
    official_api_configured,
    fetch_official_records,
    load_buyer_demands,
)
from ml import config as ml_config

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


def _source_label():
    if official_api_configured():
        return "Combined historical CSVs plus configured official API ingest"
    return "Combined historical mandi CSVs (local files). Live official API is not configured."


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
        return True
    header = request.headers.get("Authorization", "")
    provided = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not provided:
        provided = request.headers.get("X-KisanLink-Ingest-Token", "").strip()
    return provided == token


def create_app(dataframe=None, pipeline=None, load_real_data=True, load_chronos=True):
    app = Flask(__name__, static_folder=None)
    CORS(app)
    app.config["MAX_CONTENT_LENGTH"] = ml_config.INGEST_MAX_BYTES
    app.config["JSON_SORT_KEYS"] = False

    if dataframe is None and load_real_data:
        print("[KisanLink API] Loading combined mandi datasets (cache used when valid)...")
        dataframe = load_combined_data()
        print(
            f"[KisanLink API] Combined dataset ready: {len(dataframe):,} records, "
            f"{dataframe[ml_config.COL_COMMODITY].nunique()} commodities."
        )
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
        "pipeline": pipeline,
        "buyers": buyers,
        "buyer_note": buyer_note,
        "ingestion_meta": {
            "last_update": None,
            "total_records": 0 if dataframe is None else len(dataframe),
            "latest_date_in_dataset": latest,
            "live_api_connected": official_api_configured(),
            "sources": [
                {"name": "Agriculture_price_dataset.csv", "type": "historical"},
                {"name": "2022.csv", "type": "historical"},
                {"name": "2026.csv", "type": "historical"},
                {"name": "ingested/records.csv", "type": "incremental"},
            ],
        },
    }

    register_routes(app)
    return app


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
        forecast_list = []
        for i in range(ml_config.FORECAST_HORIZON):
            day_date = pd.Timestamp(latest_date) + pd.Timedelta(days=i + 1)
            forecast_list.append({
                "day": i + 1,
                "date": str(day_date.date()),
                "price": round(float(fc["median"][i]), 2),
                "p50": round(float(fc["median"][i]), 2),
                "p10": round(float(fc["low"][i]), 2),
                "p90": round(float(fc["high"][i]), 2),
                "price_low": round(float(fc["low"][i]), 2),
                "price_high": round(float(fc["high"][i]), 2),
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
        }
        if market_result.get("message"):
            response["message"] = market_result["message"]
        return jsonify(response), 200

    @app.route("/api/market-intel", methods=["GET"])
    def market_intel():
        commodity = request.args.get("commodity", "").strip()
        state = request.args.get("state", "").strip()
        district = request.args.get("district", "").strip()
        market = request.args.get("market", "").strip()
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

    @app.route("/api/market-compare", methods=["GET"])
    def market_compare():
        commodity = request.args.get("commodity", "").strip()
        state = request.args.get("state", "").strip()
        district = request.args.get("district", "").strip()
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
        latest_price = float(ctx["prices"][-1])
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
        decision["latest_actual_date"] = str(ctx["dates"].max().date())
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
        return jsonify({
            "success": True,
            "total_records": len(df),
            "latest_date_in_dataset": latest or meta.get("latest_date_in_dataset"),
            "last_ingestion_run": meta.get("last_update"),
            "sources": meta.get("sources"),
            "live_api_connected": live,
            "official_api_configured": live,
            "ingest_token_required": bool(ml_config.INGEST_TOKEN),
            "note": (
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
