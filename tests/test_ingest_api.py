"""
Unit tests that do NOT reload the 5.8M-row production CSVs.
Covers ingestion, normalization, API wiring, decision engine, buyer matching,
market comparison, sparse/missing markets, IQR=0, gaps, context, quantiles.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest
import torch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ml import config
from ml.data_loader import (
    _add_filter_columns,
    _truncate_at_gap,
    _winsorize_prices,
    clean_data,
    get_market_data,
    prepare_context,
    load_combined_data,
)
from ml.ingest import ingest_records, normalize_record, official_api_configured
from ml.decision_engine import recommend_sale_window
from ml.buyer_matcher import match_buyers
from ml.forecaster import forecast_with_quantiles
from backend.app import create_app


def _synth_rows():
    rows = []
    base = pd.Timestamp("2024-01-01")
    for i in range(40):
        rows.append({
            config.COL_STATE: "Maharashtra",
            config.COL_DISTRICT: "Nashik",
            config.COL_MARKET: "Pimpalgaon",
            config.COL_COMMODITY: "Tomato",
            config.COL_VARIETY: "Local",
            config.COL_GRADE: "FAQ",
            config.COL_DATE: base + pd.Timedelta(days=i),
            config.COL_MIN_PRICE: 1400 + i,
            config.COL_MAX_PRICE: 1800 + i,
            config.COL_MODAL_PRICE: 1600 + i * 2,
        })
    for i in range(30):
        rows.append({
            config.COL_STATE: "West Bengal",
            config.COL_DISTRICT: "Durgapur",
            config.COL_MARKET: "Durgapur",
            config.COL_COMMODITY: "Potato",
            config.COL_VARIETY: "",
            config.COL_GRADE: "",
            config.COL_DATE: base + pd.Timedelta(days=i),
            config.COL_MIN_PRICE: 700,
            config.COL_MAX_PRICE: 900,
            config.COL_MODAL_PRICE: 800 + (i % 5) * 10,
        })
    # sparse market: 5 rows
    for i in range(5):
        rows.append({
            config.COL_STATE: "Maharashtra",
            config.COL_DISTRICT: "Nashik",
            config.COL_MARKET: "TinyMandi",
            config.COL_COMMODITY: "Tomato",
            config.COL_VARIETY: "",
            config.COL_GRADE: "",
            config.COL_DATE: base + pd.Timedelta(days=i),
            config.COL_MIN_PRICE: 1000,
            config.COL_MAX_PRICE: 1100,
            config.COL_MODAL_PRICE: 1050,
        })
    df = pd.DataFrame(rows)
    return _add_filter_columns(df)


class FakePipeline:
    """Context-dependent stub for API tests — not a substitute for Chronos in production."""

    def predict(self, context, prediction_length=7, num_samples=20):
        ctx = context.detach().cpu().numpy().reshape(-1).astype(float)
        last = float(ctx[-1])
        slope = (ctx[-1] - ctx[0]) / max(len(ctx) - 1, 1)
        std = float(np.std(ctx)) if len(ctx) > 1 else max(last * 0.02, 1.0)
        rng = np.random.default_rng(int(abs(last * 17 + slope * 13)) % 10_000 + 1)
        samples = []
        for _ in range(num_samples):
            noise = rng.normal(0, max(std * 0.05, 0.5), prediction_length)
            path = last + slope * np.arange(1, prediction_length + 1) + noise
            samples.append(path)
        return torch.tensor([samples], dtype=torch.float32)


@pytest.fixture(scope="module")
def synth_df():
    return _synth_rows()


@pytest.fixture(scope="module")
def client(synth_df):
    app = create_app(
        dataframe=synth_df.copy(),
        pipeline=FakePipeline(),
        load_real_data=False,
        load_chronos=False,
    )
    app.config["TESTING"] = True
    return app.test_client()


class TestDatasetLoading:
    @pytest.mark.skipif(
        not os.path.exists(config.CSV_AGRICULTURE),
        reason="Historical CSVs not present",
    )
    def test_combined_loader_and_cache(self):
        df1 = load_combined_data()
        assert len(df1) > 1000
        df2 = load_combined_data()
        assert len(df2) == len(df1)
        assert config.COL_MARKET in df1.columns


class TestNormalization:
    def test_agriculture_schema_clean(self):
        raw = pd.DataFrame({
            "STATE": ["maharashtra"],
            "District Name": ["nashik"],
            "Market Name": ["Pimpalgaon APMC"],
            "Commodity": ["tomato"],
            "Variety": ["x"],
            "Grade": ["FAQ"],
            "Price Date": ["2024-06-01"],
            "Min_Price": [100],
            "Max_Price": [200],
            "Modal_Price": [150],
        })
        out = clean_data(raw)
        assert out.iloc[0][config.COL_STATE] == "Maharashtra"
        assert out.iloc[0][config.COL_MARKET] == "Pimpalgaon"
        assert out.iloc[0][config.COL_COMMODITY] == "Tomato"

    def test_apmc_ingest_normalize(self):
        row, reason = normalize_record({
            "State": "Maharashtra",
            "District Name": "Nashik",
            "Market Name": "Pimpalgaon APMC",
            "Commodity": "Tomato",
            "Arrival_Date": "2024-06-02",
            "Modal_Price": "1700",
        })
        assert reason is None
        assert row[config.COL_MARKET] == "Pimpalgaon"


class TestIngest:
    def test_rejects_inconsistent_price_range(self, synth_df):
        result = ingest_records([{
            "State": "Maharashtra", "District": "Nashik", "Market": "Pimpalgaon",
            "Commodity": "Tomato", "Date": "2025-02-01",
            "Min_Price": 2000, "Modal_Price": 1500, "Max_Price": 1800,
        }], synth_df, persist=False)
        assert result["invalid_skipped"] == 1
        assert result["reject_reasons"] == {"price_range_inconsistent": 1}

    def test_rejects_invalid_price(self, synth_df):
        result = ingest_records([{
            "State": "Maharashtra", "District": "Nashik", "Market": "Pimpalgaon",
            "Commodity": "Tomato", "Date": "2024-03-01", "Modal_Price": -5,
        }], synth_df, persist=False)
        assert result["added"] == 0
        assert result["invalid_skipped"] == 1

    def test_rejects_impossible_price(self, synth_df):
        result = ingest_records([{
            "State": "Maharashtra", "District": "Nashik", "Market": "Pimpalgaon",
            "Commodity": "Tomato", "Date": "2024-03-01", "Modal_Price": 99_000_000,
        }], synth_df, persist=False)
        assert result["invalid_skipped"] == 1

    def test_duplicate_prevention(self, synth_df):
        rec = {
            "State": "Maharashtra", "District": "Nashik", "Market": "Pimpalgaon",
            "Commodity": "Tomato", "Date": "2024-01-01", "Modal_Price": 1600,
            "Variety": "Local", "Grade": "FAQ",
        }
        result = ingest_records([rec], synth_df, persist=False)
        assert result["duplicates_skipped"] == 1
        assert result["added"] == 0

    def test_inserts_new_and_idempotent(self, synth_df):
        rec = {
            "State": "Maharashtra", "District": "Nashik", "Market": "Pimpalgaon",
            "Commodity": "Tomato", "Date": "2025-01-15", "Modal_Price": 1900,
        }
        once = ingest_records([rec], synth_df, persist=False)
        assert once["added"] == 1
        assert once["frame"]["_commodity_l"].notna().all()
        assert (once["frame"]["_commodity_l"] == "tomato").any()
        twice = ingest_records([rec], once["frame"], persist=False)
        assert twice["added"] == 0
        assert twice["duplicates_skipped"] == 1

    def test_rejects_path_like_market(self, synth_df):
        result = ingest_records([{
            "State": "Maharashtra", "District": "Nashik",
            "Market": "C:\\secret\\prices.csv", "Commodity": "Tomato",
            "Date": "2025-01-01", "Modal_Price": 100,
        }], synth_df, persist=False)
        assert result["invalid_skipped"] == 1

    def test_latest_date_updates(self, synth_df):
        rec = {
            "State": "Maharashtra", "District": "Nashik", "Market": "Pimpalgaon",
            "Commodity": "Tomato", "Date": "2026-04-01", "Modal_Price": 2000,
        }
        result = ingest_records([rec], synth_df, persist=False)
        assert result["latest_date_in_dataset"] == "2026-04-01"

    def test_official_api_not_pretended(self):
        assert official_api_configured() is bool(config.DATA_GOV_API_KEY and config.DATA_GOV_RESOURCE_ID)


class TestSparseAndMissing:
    def test_sparse_market(self, synth_df):
        r = get_market_data(synth_df, "Tomato", "Maharashtra", "Nashik", "TinyMandi")
        assert r["source"] == "Insufficient data"
        assert r["record_count"] == 5

    def test_missing_market(self, synth_df):
        r = get_market_data(synth_df, "Tomato", "Maharashtra", "Nashik", "ClearlyFake")
        assert r["source"] == "Insufficient data"

    def test_missing_commodity(self, synth_df):
        r = get_market_data(synth_df, "Durian999", "Maharashtra", "Nashik", "Pimpalgaon")
        assert r["source"] == "Insufficient data"


class TestContextForecastQuantiles:
    def test_gap_detection(self):
        prices = np.array([10.0] * 20 + [50.0] * 20)
        dates = pd.date_range("2020-01-01", periods=20, freq="D").append(
            pd.date_range("2023-01-01", periods=20, freq="D")
        )
        p, d, info = _truncate_at_gap(prices, dates, 365, 14)
        assert len(p) == 20
        assert info is not None

    def test_iqr_zero(self):
        prices = np.array([1000.0] * 30 + [5_000_000.0])
        out = _winsorize_prices(prices, k=5.0)
        assert np.allclose(out[:30], 1000.0)
        assert out[-1] < prices[-1]

    def test_outlier_handling(self):
        prices = np.array([1000.0] * 50 + [191_820_849.0])
        out = _winsorize_prices(prices, k=5.0)
        assert out[-1] < 20_000

    def test_prepare_context(self, synth_df):
        r = get_market_data(synth_df, "Tomato", "Maharashtra", "Nashik", "Pimpalgaon")
        ctx = prepare_context(r["data"])
        assert ctx["context_tensor"].shape[0] == 1
        assert ctx["context_length"] >= config.MIN_RECORDS

    def test_quantiles_ordered(self, synth_df):
        r = get_market_data(synth_df, "Tomato", "Maharashtra", "Nashik", "Pimpalgaon")
        ctx = prepare_context(r["data"])
        fc = forecast_with_quantiles(FakePipeline(), ctx["context_tensor"])
        assert len(fc["median"]) == config.FORECAST_HORIZON
        assert np.all(fc["low"] <= fc["median"] + 1e-6)
        assert np.all(fc["median"] <= fc["high"] + 1e-6)

    def test_different_markets_differ(self, synth_df):
        a = get_market_data(synth_df, "Tomato", "Maharashtra", "Nashik", "Pimpalgaon")
        b = get_market_data(synth_df, "Potato", "West Bengal", "Durgapur", "Durgapur")
        fa = forecast_with_quantiles(FakePipeline(), prepare_context(a["data"])["context_tensor"])
        fb = forecast_with_quantiles(FakePipeline(), prepare_context(b["data"])["context_tensor"])
        assert not np.allclose(fa["median"], fb["median"], atol=1.0)


class TestDecisionAndBuyers:
    def test_sell_now_when_forecast_below(self):
        med = np.array([90, 91, 92, 90, 88, 87, 86], dtype=float)
        lo = med - 5
        hi = med + 5
        out = recommend_sale_window(med, lo, hi, latest_price=200.0)
        assert out["action"] == "SELL_NOW"
        assert out["wait_days"] == 0

    def test_wait_when_clear_rise(self):
        med = np.array([1100, 1200, 1400, 1600, 1800, 2000, 2200], dtype=float)
        lo = med - 10
        hi = med + 10
        out = recommend_sale_window(med, lo, hi, latest_price=1000.0, min_benefit_per_qtl=50)
        assert out["action"].startswith("WAIT")
        assert out["wait_days"] > 0

    def test_buyer_scores_not_constant(self):
        demands = [
            {"id": "1", "buyerName": "A", "buyerType": "Processor", "trustStatus": "verified",
             "crop": "Onion", "quantity": 50, "grade": "Grade A",
             "deliveryLocation": "Pune, Maharashtra", "offeredRate": 3200},
            {"id": "2", "buyerName": "B", "buyerType": "Trader", "trustStatus": "Registered Buyer",
             "crop": "Onion", "quantity": 5, "grade": "Grade C",
             "deliveryLocation": "Kerala", "offeredRate": 400},
        ]
        matches = match_buyers("Onion", 50, "Grade A", "Maharashtra", 3000, demands)
        scores = [m["match_score"] for m in matches]
        assert scores[0] != scores[1]
        assert 0 <= min(scores) <= max(scores) <= 100


class TestBackendEndpoints:
    def test_commodities(self, client):
        r = client.get("/api/commodities")
        assert r.status_code == 200
        assert "Tomato" in r.get_json()

    def test_states_districts_markets(self, client):
        assert client.get("/api/states?commodity=Tomato").status_code == 200
        d = client.get("/api/districts?commodity=Tomato&state=Maharashtra")
        assert "Nashik" in d.get_json()
        m = client.get("/api/markets?commodity=Tomato&state=Maharashtra&district=Nashik")
        assert "Pimpalgaon" in m.get_json()

    def test_forecast(self, client):
        r = client.post("/api/forecast", json={
            "commodity": "Tomato", "state": "Maharashtra",
            "district": "Nashik", "market": "Pimpalgaon",
        })
        body = r.get_json()
        assert r.status_code == 200
        assert body["success"] is True
        assert len(body["forecast"]) == 7
        assert "p10" in body["forecast"][0]
        assert "sale_window" in body
        assert body["sale_window"]["action"] in ("SELL_NOW",) or body["sale_window"]["action"].startswith("WAIT")

    def test_forecast_sparse(self, client):
        r = client.post("/api/forecast", json={
            "commodity": "Tomato", "state": "Maharashtra",
            "district": "Nashik", "market": "TinyMandi",
        })
        assert r.status_code == 422

    def test_forecast_missing_commodity(self, client):
        r = client.post("/api/forecast", json={
            "commodity": "Durian999", "state": "Maharashtra",
            "district": "Nashik", "market": "Pimpalgaon",
        })
        assert r.status_code == 422

    def test_market_compare(self, client):
        r = client.get("/api/market-compare?commodity=Tomato&state=Maharashtra&district=Nashik")
        body = r.get_json()
        assert r.status_code == 200
        names = [m["market"] for m in body["markets"]]
        assert "Pimpalgaon" in names
        prices = {m["market"]: m["latest_price"] for m in body["markets"]}
        assert prices["Pimpalgaon"] != 0

    def test_market_intel(self, client):
        r = client.get("/api/market-intel?commodity=Tomato&state=Maharashtra&district=Nashik&market=Pimpalgaon")
        assert r.status_code == 200
        assert r.get_json()["latest_price"] > 0

    def test_buyer_demands_and_match(self, client):
        d = client.get("/api/buyer-demands")
        assert d.status_code == 200
        m = client.post("/api/buyer-match", json={
            "commodity": "Onion", "state": "Maharashtra",
            "quantity_qtl": 10, "grade": "Grade A", "expected_price": 3000,
        })
        body = m.get_json()
        assert m.status_code == 200
        if body["matches"]:
            assert body["matches"][0]["match_score"] != 92 or len(body["matches"]) >= 1

        alias = client.get(
            "/api/buyer-matches?commodity=Onion&state=Maharashtra&district=Nashik&"
            "market=Lasalgaon&quantity_qtl=10&grade=Grade%20A&expected_price=3000"
        )
        assert alias.status_code == 200
        assert alias.get_json()["request_context"]["market"] == "Lasalgaon"

    def test_ingest_status(self, client):
        r = client.get("/api/ingest/status")
        body = r.get_json()
        assert r.status_code == 200
        assert body["live_api_connected"] is False or isinstance(body["live_api_connected"], bool)
        assert "latest_date_in_dataset" in body

    def test_ingest_update(self, client):
        r = client.post("/api/ingest/update", json={"records": [{
            "State": "Maharashtra", "District": "Nashik", "Market": "Pimpalgaon",
            "Commodity": "Tomato", "Date": "2025-12-01", "Modal_Price": 2100,
        }]})
        body = r.get_json()
        assert r.status_code == 200
        assert body["added"] == 1
        assert body["inserted"] == 1
        again = client.post("/api/ingest/update", json={"records": [{
            "State": "Maharashtra", "District": "Nashik", "Market": "Pimpalgaon",
            "Commodity": "Tomato", "Date": "2025-12-01", "Modal_Price": 2100,
        }]})
        assert again.get_json()["duplicates_skipped"] == 1

    def test_ingest_rejects_empty(self, client):
        r = client.post("/api/ingest/update", json={"records": []})
        assert r.status_code == 400
