"""
Tests for the live-mandi adapter, price sanity, routing, geocoding validation,
net realisation, sell-now ranking, lot creation, and market-price filtering.

These never hit the network: `KISANLINK_DISABLE_EXTERNAL` is forced on and the
app is created with `TESTING=True`, which makes `_allow_external_http()` false.
Anything that would call data.gov.in, Nominatim, OSRM, or OpenRouteService must
therefore take its documented offline path.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# `services` is a package inside backend/, which backend.app puts on the path
# at import time; tests import it directly so add it up front.
sys.path.insert(0, os.path.join(ROOT, "backend"))

os.environ.setdefault("KISANLINK_DISABLE_EXTERNAL", "1")

from ml import config
from ml import dev_fixture
from ml.data_loader import _add_filter_columns
from ml.price_sanity import recent_anchor, sanitize_forecast
from ml.transport import (
    net_realisation,
    transport_cost_per_qtl,
    transport_loading_rate,
    transport_rate,
)
from services.geocode import validate_coords
from services.mandi_live import fetch_live_prices
from services.routing import compute_route
from backend.app import create_app


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _frame():
    """Two commodities across markets at different distances from Nashik."""
    rows = []
    base = pd.Timestamp("2026-01-01")
    markets = [
        # (state, district, market, modal price)
        ("Maharashtra", "Nashik", "Pimpalgaon", 2000.0),   # local, low freight
        ("Maharashtra", "Pune", "Pune Market Yard", 2120.0),  # ~165 km
        ("Maharashtra", "Solapur", "Solapur", 2400.0),     # far: highest sticker
    ]
    for state, district, market, price in markets:
        for i in range(40):
            rows.append({
                config.COL_STATE: state,
                config.COL_DISTRICT: district,
                config.COL_MARKET: market,
                config.COL_COMMODITY: "Onion",
                config.COL_VARIETY: "Red",
                config.COL_GRADE: "FAQ",
                config.COL_DATE: base + pd.Timedelta(days=i),
                config.COL_MIN_PRICE: price - 100,
                config.COL_MAX_PRICE: price + 100,
                config.COL_MODAL_PRICE: price,
            })
    for i in range(30):
        rows.append({
            config.COL_STATE: "Karnataka",
            config.COL_DISTRICT: "Belagavi",
            config.COL_MARKET: "Belagavi",
            config.COL_COMMODITY: "Potato",
            config.COL_VARIETY: "",
            config.COL_GRADE: "",
            config.COL_DATE: base + pd.Timedelta(days=i),
            config.COL_MIN_PRICE: 1100,
            config.COL_MAX_PRICE: 1300,
            config.COL_MODAL_PRICE: 1200,
        })
    return _add_filter_columns(pd.DataFrame(rows))


@pytest.fixture(scope="module")
def client():
    app = create_app(dataframe=_frame(), pipeline=None,
                     load_real_data=False, load_chronos=False)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def auth_headers(client):
    """Register a farmer and return an Authorization header."""
    import uuid
    suffix = uuid.uuid4().hex[:10]
    res = client.post("/api/auth/register", json={
        "name": "Test Farmer",
        "username": f"farmer_{suffix}",
        "phone": "9" + suffix[:9].translate(str.maketrans("abcdef", "123456")),
        "password": "StrongPass!234",
        "role": "FARMER",
        "district": "Nashik",
        "state": "Maharashtra",
    })
    assert res.status_code in (200, 201), res.get_json()
    token = res.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. live mandi response normalization + fallback
# ---------------------------------------------------------------------------

class TestLiveMandiAdapter:
    def test_unconfigured_never_claims_live(self, monkeypatch):
        monkeypatch.setattr(config, "DATA_GOV_API_KEY", "")
        monkeypatch.setattr(config, "DATA_GOV_RESOURCE_ID", "")
        out = fetch_live_prices(commodity="Onion")
        assert out["success"] is False
        assert out["configured"] is False
        assert out["live"] is False
        assert out["records"] == []
        assert "DATA_GOV_API_KEY" in out["error"]

    def test_endpoint_reports_unavailable_without_credentials(self, client, monkeypatch):
        monkeypatch.setattr(config, "DATA_GOV_API_KEY", "")
        monkeypatch.setattr(config, "DATA_GOV_RESOURCE_ID", "")
        res = client.get("/api/market-prices/live?commodity=Onion")
        assert res.status_code == 200
        body = res.get_json()
        assert body["is_live"] is False
        assert body["label"] == "Live mandi feed unavailable"

    def test_normalizes_mixed_case_field_names(self, monkeypatch):
        """data.gov.in has shipped both Modal_Price and modal_price."""
        import services.mandi_live as ml

        payload = {"records": [
            {"state": "Maharashtra", "district": "Nashik", "market": "Pimpalgaon",
             "commodity": "Onion", "variety": "Red", "grade": "FAQ",
             "arrival_date": "05/01/2026",
             "min_price": "1800", "max_price": "2200", "modal_price": "2000"},
            {"State": "Maharashtra", "District": "Pune", "Market": "Pune",
             "Commodity": "Onion", "Variety": "Local", "Grade": "FAQ",
             "Arrival_Date": "05/01/2026",
             "Min_Price": "1900", "Max_Price": "2300", "Modal_Price": "2100"},
        ]}

        monkeypatch.setattr(config, "DATA_GOV_API_KEY", "test-key")
        monkeypatch.setattr(config, "DATA_GOV_RESOURCE_ID", "test-resource")
        monkeypatch.setattr(ml, "_CACHE", {})

        class _Resp:
            def read(self):
                return json.dumps(payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(ml.urllib.request, "urlopen", lambda *a, **k: _Resp())

        out = ml.fetch_live_prices(commodity="Onion")
        assert out["success"] is True
        assert out["count"] == 2
        modal = sorted(r["modal_price"] for r in out["records"])
        assert modal == [2000.0, 2100.0]
        # both spellings land on the same canonical keys
        for rec in out["records"]:
            assert set(["commodity", "state", "district", "market",
                        "modal_price", "min_price", "max_price",
                        "arrival_date", "unit"]).issubset(rec)
            assert rec["unit"] == "INR per quintal"
            assert rec["commodity"] == "Onion"

    def test_old_rows_are_not_labelled_live(self, monkeypatch):
        """A successful fetch of stale rows is 'latest available', never LIVE."""
        import services.mandi_live as ml

        payload = {"records": [
            {"state": "Maharashtra", "district": "Nashik", "market": "Pimpalgaon",
             "commodity": "Onion", "arrival_date": "01/01/2020",
             "min_price": "1800", "max_price": "2200", "modal_price": "2000"},
        ]}
        monkeypatch.setattr(config, "DATA_GOV_API_KEY", "k")
        monkeypatch.setattr(config, "DATA_GOV_RESOURCE_ID", "r")
        monkeypatch.setattr(ml, "_CACHE", {})

        class _Resp:
            def read(self): return json.dumps(payload).encode("utf-8")
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(ml.urllib.request, "urlopen", lambda *a, **k: _Resp())
        out = ml.fetch_live_prices(commodity="Onion")
        assert out["success"] is True
        assert out["live"] is False
        assert out["label"] == "LATEST AVAILABLE MANDI DATA"
        assert out["records"][0]["is_today"] is False

    def test_api_failure_falls_back_without_inventing_rows(self, monkeypatch):
        import services.mandi_live as ml
        monkeypatch.setattr(config, "DATA_GOV_API_KEY", "k")
        monkeypatch.setattr(config, "DATA_GOV_RESOURCE_ID", "r")
        monkeypatch.setattr(ml, "_CACHE", {})

        def _boom(*a, **k):
            raise OSError("network down")

        monkeypatch.setattr(ml.urllib.request, "urlopen", _boom)
        out = ml.fetch_live_prices(commodity="Onion")
        assert out["success"] is False
        assert out["live"] is False
        assert out["records"] == []
        assert out["configured"] is True


# ---------------------------------------------------------------------------
# 2. price sanity
# ---------------------------------------------------------------------------

class TestPriceSanity:
    def test_absurd_forecast_is_replaced_by_last_real_price(self):
        history = [2000.0] * 30
        out = sanitize_forecast(
            low=np.full(7, 90_000.0),
            median=np.full(7, 97_631.0),   # the reported ₹97,631/QTL failure
            high=np.full(7, 110_000.0),
            recent_prices=history,
        )
        assert out["applied"] is True
        assert float(np.max(out["median"])) < 3000
        assert pytest.approx(float(out["median"][0]), rel=1e-6) == 2000.0
        assert out["notes"]

    def test_plausible_forecast_is_left_alone(self):
        history = list(np.linspace(1900, 2100, 30))
        median = np.linspace(2100, 2150, 7)
        out = sanitize_forecast(median * 0.97, median, median * 1.03, history)
        assert out["applied"] is False
        assert np.allclose(out["median"], median)

    def test_quantile_ordering_is_preserved(self):
        history = [2000.0] * 30
        out = sanitize_forecast(
            np.full(7, 500_000.0), np.full(7, 600_000.0),
            np.full(7, 700_000.0), history,
        )
        assert np.all(out["low"] <= out["median"])
        assert np.all(out["median"] <= out["high"])

    def test_anchor_ignores_non_positive_values(self):
        stats = recent_anchor([0, -5, np.nan, 1000, 1100, 1200])
        assert stats["anchor"] is not None
        assert stats["last"] == 1200


# ---------------------------------------------------------------------------
# 3. GPS payload handling
# ---------------------------------------------------------------------------

class TestGpsPayload:
    @pytest.mark.parametrize("lat,lon", [
        (91, 73.0), (-91, 73.0), (19.0, 181.0), (19.0, -181.0),
        ("abc", 73.0), (None, 73.0),
    ])
    def test_invalid_coordinates_rejected(self, lat, lon):
        _la, _lo, err = validate_coords(lat, lon)
        assert err is not None

    def test_valid_coordinates_accepted(self):
        lat, lon, err = validate_coords("19.9975", "73.7898")
        assert err is None
        assert lat == pytest.approx(19.9975)
        assert lon == pytest.approx(73.7898)

    def test_sell_now_rejects_out_of_range_gps(self, client):
        res = client.post("/api/sell-now", json={
            "commodity": "Onion", "state": "Maharashtra", "district": "Nashik",
            "quantity_qtl": 10, "lat": 999, "lon": 73.0,
        })
        assert res.status_code == 400
        assert res.get_json()["success"] is False

    def test_sell_now_rejects_half_supplied_gps(self, client):
        res = client.post("/api/sell-now", json={
            "commodity": "Onion", "state": "Maharashtra", "district": "Nashik",
            "quantity_qtl": 10, "lat": 19.9,
        })
        assert res.status_code == 400

    def test_sell_now_accepts_and_reports_gps_origin(self, client):
        res = client.post("/api/sell-now", json={
            "commodity": "Onion", "state": "Maharashtra", "district": "Nashik",
            "quantity_qtl": 10, "lat": 19.9975, "lon": 73.7898,
        })
        assert res.status_code == 200
        body = res.get_json()
        assert body["origin_gps_used"] is True
        assert body["origin_coords_source"] == "browser_gps"

    def test_sell_now_without_gps_does_not_claim_it(self, client):
        res = client.post("/api/sell-now", json={
            "commodity": "Onion", "state": "Maharashtra",
            "district": "Nashik", "quantity_qtl": 10,
        })
        assert res.get_json()["origin_gps_used"] is False

    def test_reverse_geocode_endpoint_validates_input(self, client):
        assert client.get("/api/location/reverse?lat=999&lon=73").status_code == 400

    def test_reverse_geocode_offline_is_explicit_not_guessed(self, client):
        res = client.get("/api/location/reverse?lat=19.99&lon=73.78")
        assert res.status_code == 503
        body = res.get_json()
        assert body["success"] is False
        # It must not invent a district.
        assert "district" not in body or not body.get("district")


# ---------------------------------------------------------------------------
# 4. routing
# ---------------------------------------------------------------------------

class TestRouting:
    def test_offline_fallback_is_labelled_estimated(self):
        out = compute_route(19.9975, 73.7898, 18.5204, 73.8567, allow_network=False)
        assert out["success"] is True
        assert out["estimated"] is True
        assert out["source"] == "haversine"
        assert out["duration_minutes"] is None      # never fabricates a travel time
        assert "straight-line" in out["note"].lower()

    def test_fallback_distance_is_physically_sensible(self):
        out = compute_route(19.9975, 73.7898, 18.5204, 73.8567, allow_network=False)
        # Nashik -> Pune is ~165 km by road, ~165 km straight line is ~163.
        assert 140 <= out["distance_km"] <= 190

    def test_invalid_coordinates_rejected(self):
        out = compute_route(999, 73.0, 18.5, 73.8, allow_network=False)
        assert out["success"] is False
        assert "Invalid origin" in out["error"]

    def test_route_endpoint_labels_estimate(self, client):
        res = client.post("/api/route", json={
            "origin": {"lat": 19.9975, "lon": 73.7898},
            "destination": {"lat": 18.5204, "lon": 73.8567},
        })
        assert res.status_code == 200
        body = res.get_json()
        assert body["estimated"] is True
        assert body["source"] == "haversine"

    def test_route_endpoint_rejects_bad_payload(self, client):
        assert client.post("/api/route", json={"origin": {}, "destination": {}}).status_code == 400


# ---------------------------------------------------------------------------
# 5. net realisation
# ---------------------------------------------------------------------------

class TestNetRealisation:
    def test_arithmetic_is_exact(self):
        out = net_realisation(2000.0, 25.0, 100.0)
        gross = 2000.0 * 25
        assert out["gross_sale_value"] == pytest.approx(gross)
        expected_freight = (transport_loading_rate() + transport_rate() * 100) * 25
        assert out["transport_cost"] == pytest.approx(expected_freight, rel=1e-6)
        assert out["handling_cost"] == pytest.approx(15.0 * 25)
        assert out["mandi_fee_estimate"] == pytest.approx(gross * 0.01)
        assert out["net_realisation"] == pytest.approx(
            gross - expected_freight - 15.0 * 25 - gross * 0.01, rel=1e-6
        )

    def test_freight_is_two_part_and_monotonic(self):
        near = transport_cost_per_qtl(10)
        far = transport_cost_per_qtl(300)
        assert far > near
        # fixed component means a zero-distance trip still costs something
        assert transport_cost_per_qtl(0) == pytest.approx(transport_loading_rate())

    def test_freight_does_not_exceed_crop_value_on_a_long_haul(self):
        """Regression: a flat ₹8/QTL/km put ₹60k of freight on ₹48k of onions."""
        out = net_realisation(2000.0, 25.0, 300.0)
        assert out["transport_cost"] < out["gross_sale_value"] * 0.35
        assert out["net_realisation"] > 0

    def test_net_falls_as_distance_grows(self):
        near = net_realisation(2000.0, 25.0, 10.0)["net_realisation"]
        far = net_realisation(2000.0, 25.0, 250.0)["net_realisation"]
        assert near > far

    def test_zero_quantity_is_safe(self):
        out = net_realisation(2000.0, 0.0, 50.0)
        assert out["gross_sale_value"] == 0
        assert out["net_realisation"] == 0


# ---------------------------------------------------------------------------
# 6. sell-now ranking
# ---------------------------------------------------------------------------

class TestSellNow:
    def test_requires_core_fields(self, client):
        assert client.post("/api/sell-now", json={"commodity": "Onion"}).status_code == 400

    def test_rejects_non_positive_quantity(self, client):
        res = client.post("/api/sell-now", json={
            "commodity": "Onion", "state": "Maharashtra",
            "district": "Nashik", "quantity_qtl": 0,
        })
        assert res.status_code == 400

    def test_unknown_commodity_is_a_clear_error(self, client):
        res = client.post("/api/sell-now", json={
            "commodity": "Dragonfruit", "state": "Maharashtra",
            "district": "Nashik", "quantity_qtl": 10,
        })
        assert res.status_code == 422

    def test_ranks_by_net_realisation_not_sticker_price(self, client):
        res = client.post("/api/sell-now", json={
            "commodity": "Onion", "state": "Maharashtra",
            "district": "Nashik", "quantity_qtl": 50,
        })
        assert res.status_code == 200
        body = res.get_json()
        markets = body["markets"]
        assert len(markets) >= 2
        nets = [m["net_realisation"] for m in markets]
        assert nets == sorted(nets, reverse=True), nets
        assert body["recommended"]["market"] == markets[0]["market"]

    def test_each_market_carries_the_full_cost_breakdown(self, client):
        body = client.post("/api/sell-now", json={
            "commodity": "Onion", "state": "Maharashtra",
            "district": "Nashik", "quantity_qtl": 20,
        }).get_json()
        for m in body["markets"]:
            for key in ("modal_price", "distance_km", "transport_cost",
                        "handling_cost", "mandi_fee_estimate", "total_cost",
                        "net_realisation", "net_per_qtl", "latest_date"):
                assert key in m, key
            # gross - costs must reconcile
            assert m["net_realisation"] == pytest.approx(
                m["gross_sale_value"] - m["total_cost"], rel=1e-4)

    def test_offline_distances_are_flagged_estimated(self, client):
        body = client.post("/api/sell-now", json={
            "commodity": "Onion", "state": "Maharashtra",
            "district": "Nashik", "quantity_qtl": 20,
        }).get_json()
        assert all(m["distance_estimated"] for m in body["markets"])
        assert "straight-line" in body["distance_disclaimer"].lower()

    def test_response_explains_and_disclaims(self, client):
        body = client.post("/api/sell-now", json={
            "commodity": "Onion", "state": "Maharashtra",
            "district": "Nashik", "quantity_qtl": 20,
        }).get_json()
        assert body["explanation"]
        assert "not an official" in body["cost_disclaimer"].lower()
        assert body["live_feed"]["live"] is False

    def test_no_market_is_labelled_live_without_a_live_feed(self, client):
        body = client.post("/api/sell-now", json={
            "commodity": "Onion", "state": "Maharashtra",
            "district": "Nashik", "quantity_qtl": 20,
        }).get_json()
        assert not any(m["is_live_price"] for m in body["markets"])


# ---------------------------------------------------------------------------
# 7. market price filtering
# ---------------------------------------------------------------------------

class TestMarketPriceFiltering:
    def test_commodity_is_required(self, client):
        assert client.get("/api/market-prices/latest").status_code == 400

    def test_returns_variety_and_source(self, client):
        body = client.get("/api/market-prices/latest?commodity=Onion").get_json()
        assert body["count"] > 0
        row = body["prices"][0]
        assert row["variety"] == "Red"
        assert row["source"]
        assert row["unit"] == "₹/Quintal"

    def test_state_filter_narrows_results(self, client):
        all_rows = client.get("/api/market-prices/latest?commodity=Onion").get_json()
        mh = client.get("/api/market-prices/latest?commodity=Onion&state=Maharashtra").get_json()
        assert mh["count"] <= all_rows["count"]
        assert all(r["state"] == "Maharashtra" for r in mh["prices"])

    def test_district_filter_narrows_results(self, client):
        body = client.get(
            "/api/market-prices/latest?commodity=Onion&state=Maharashtra&district=Pune"
        ).get_json()
        assert body["count"] >= 1
        assert all(r["district"] == "Pune" for r in body["prices"])

    def test_market_filter_narrows_results(self, client):
        body = client.get(
            "/api/market-prices/latest?commodity=Onion&market=Pimpalgaon"
        ).get_json()
        assert all(r["market"] == "Pimpalgaon" for r in body["prices"])

    def test_unknown_commodity_returns_empty_not_error(self, client):
        body = client.get("/api/market-prices/latest?commodity=Dragonfruit").get_json()
        assert body["success"] is True
        assert body["count"] == 0

    def test_historical_data_is_never_labelled_live(self, client):
        body = client.get("/api/market-prices/latest?commodity=Onion").get_json()
        assert body["is_live"] is False
        assert body["is_live_today"] is False
        assert body["latest_date"]
        assert "live" not in body["label"].lower()

    def test_prices_stay_on_a_sane_scale(self, client):
        body = client.get("/api/market-prices/latest?commodity=Onion").get_json()
        for row in body["prices"]:
            assert 100 < row["modal_price"] < 50_000
            if row["min_price"] and row["max_price"]:
                assert row["min_price"] <= row["modal_price"] <= row["max_price"]


# ---------------------------------------------------------------------------
# 8. create lot
# ---------------------------------------------------------------------------

class TestCreateLot:
    def test_requires_authentication(self, client):
        assert client.post("/api/lots", json={"commodity": "Onion",
                                              "quantity_qtl": 10}).status_code == 401

    def test_creates_and_persists_a_lot(self, client, auth_headers):
        res = client.post("/api/lots", headers=auth_headers, json={
            "commodity": "Onion", "variety": "Red", "quantity_qtl": 25,
            "unit": "QTL", "grade": "Grade A", "location": "Nashik, Maharashtra",
            "district": "Nashik", "state": "Maharashtra", "market": "Lasalgaon",
            "harvest_date": "2026-09-12", "price_per_qtl": 1943,
        })
        assert res.status_code == 201, res.get_json()
        lot = res.get_json()["lot"]
        assert lot["id"]
        assert lot["commodity"] == "Onion"
        assert lot["market"] == "Lasalgaon"

        mine = client.get("/api/lots/my", headers=auth_headers).get_json()
        assert any(l["id"] == lot["id"] for l in mine["lots"])

        single = client.get(f"/api/lots/{lot['id']}").get_json()
        assert single["lot"]["quantity_qtl"] == 25

    def test_price_per_qtl_is_reconciled_to_expected_price(self, client, auth_headers):
        """The form posts price_per_qtl; the DB column is expected_price."""
        res = client.post("/api/lots", headers=auth_headers, json={
            "commodity": "Onion", "quantity_qtl": 10,
            "location": "Nashik, Maharashtra", "price_per_qtl": 2222,
        })
        assert res.status_code == 201
        assert res.get_json()["lot"]["expected_price"] == 2222

    def test_expected_price_alias_also_accepted(self, client, auth_headers):
        res = client.post("/api/lots", headers=auth_headers, json={
            "commodity": "Onion", "quantity_qtl": 10,
            "location": "Nashik, Maharashtra", "expectedPrice": 3333,
        })
        assert res.status_code == 201
        assert res.get_json()["lot"]["expected_price"] == 3333

    def test_district_is_derived_from_location_when_absent(self, client, auth_headers):
        res = client.post("/api/lots", headers=auth_headers, json={
            "commodity": "Onion", "quantity_qtl": 10,
            "location": "Dindori, Nashik",
        })
        assert res.status_code == 201
        assert res.get_json()["lot"]["district"] == "Dindori"

    def test_rejects_missing_commodity_and_bad_quantity(self, client, auth_headers):
        assert client.post("/api/lots", headers=auth_headers,
                           json={"quantity_qtl": 5}).status_code == 400
        assert client.post("/api/lots", headers=auth_headers,
                           json={"commodity": "Onion",
                                 "quantity_qtl": 0}).status_code == 400
        assert client.post("/api/lots", headers=auth_headers,
                           json={"commodity": "Onion",
                                 "quantity_qtl": "many"}).status_code == 400


# ---------------------------------------------------------------------------
# 9. development fixture honesty
# ---------------------------------------------------------------------------

class TestDevFixtureHonesty:
    def test_disabled_unless_explicitly_enabled(self, monkeypatch):
        monkeypatch.delenv(dev_fixture.ENV_FLAG, raising=False)
        assert dev_fixture.enabled() is False
        monkeypatch.setenv(dev_fixture.ENV_FLAG, "1")
        assert dev_fixture.enabled() is True

    def test_source_label_says_it_is_not_real_data(self):
        label = dev_fixture.SOURCE_LABEL.lower()
        assert "synthetic" in label
        assert "not real mandi data" in label

    def test_generated_prices_are_on_a_believable_scale(self):
        frame = dev_fixture.build_frame(days=30)
        modal = frame[config.COL_MODAL_PRICE]
        assert not frame.empty
        assert modal.min() > 400
        assert modal.max() < 20_000
        assert (frame[config.COL_MIN_PRICE] <= modal).all()
        assert (frame[config.COL_MAX_PRICE] >= modal).all()

    def test_fixture_backed_app_never_claims_live_or_today(self, monkeypatch):
        monkeypatch.setenv(dev_fixture.ENV_FLAG, "1")
        app = create_app(dataframe=dev_fixture.build_frame(days=30), pipeline=None,
                         load_real_data=False, load_chronos=False)
        app.config["TESTING"] = True
        # Simulate the fixture path having been taken.
        app.extensions["kisanlink"]["dev_fixture"] = True
        c = app.test_client()

        body = c.get("/api/market-prices/latest?commodity=Onion").get_json()
        assert body["dev_fixture"] is True
        assert body["is_live"] is False
        assert body["is_live_today"] is False
        assert "sample data" in body["label"].lower()
        assert all(r["source"] == "Synthetic development fixture" for r in body["prices"])

        status = c.get("/api/ingest/status").get_json()
        assert status["dev_fixture"] is True
        assert "synthetic" in status["data_source_label"].lower()


# ---------------------------------------------------------------------------
# 10. auth, privacy and error hygiene
# ---------------------------------------------------------------------------

class TestAuthAndPrivacy:
    def test_password_hash_never_leaves_the_api(self, client):
        import uuid
        suffix = uuid.uuid4().hex[:10]
        reg = client.post("/api/auth/register", json={
            "name": "Privacy Probe", "username": f"priv_{suffix}",
            "phone": "9" + suffix[:9].translate(str.maketrans("abcdef", "123456")),
            "password": "StrongPass!234", "role": "FARMER",
            "district": "Nashik", "state": "Maharashtra",
        })
        assert reg.status_code in (200, 201)
        body = reg.get_data(as_text=True)
        assert "password_hash" not in body
        assert "StrongPass!234" not in body

        token = reg.get_json()["token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert "password_hash" not in me.get_data(as_text=True)

    @pytest.mark.parametrize("method,path", [
        ("get", "/api/auth/me"),
        ("get", "/api/lots/my"),
        ("post", "/api/lots"),
        ("get", "/api/transactions/my"),
        ("get", "/api/buyer-requirements/my"),
        ("post", "/api/buyer-requirements"),
        ("get", "/api/offers/my"),
    ])
    def test_protected_endpoints_reject_anonymous_callers(self, client, method, path):
        res = getattr(client, method)(path, json={} if method == "post" else None)
        assert res.status_code == 401, f"{path} returned {res.status_code}"

    def test_bad_token_is_rejected(self, client):
        res = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
        assert res.status_code == 401

    def test_farmer_cannot_post_a_buyer_requirement(self, client, auth_headers):
        res = client.post("/api/buyer-requirements", headers=auth_headers,
                          json={"commodity": "Onion", "quantity_qtl_min": 10})
        assert res.status_code == 403


class TestErrorHygiene:
    """Failures must not hand internal exception text to the browser."""

    def test_static_data_endpoints_do_not_return_raw_exception_detail(self, client):
        for path in ("/api/schemes", "/api/knowledge", "/api/learning",
                     "/api/helplines", "/api/seeds"):
            body = client.get(path).get_json()
            assert "detail" not in body, path

    def test_weather_failure_is_a_clean_message(self, client):
        # TESTING=True disables outbound HTTP, so this always takes the fail path.
        res = client.get("/api/weather?district=Nashik&state=Maharashtra")
        body = res.get_json()
        if not body.get("success"):
            assert "detail" not in body
            text = body.get("error", "")
            for leak in ("Traceback", "urlopen", "_ssl.c", "/home/", "site-packages"):
                assert leak not in text, text


class TestSeedBuyerProvenance:
    def test_seed_buyers_are_generic_placeholders_not_real_firms(self):
        from ml.ingest import load_buyer_demands
        demands, note = load_buyer_demands()
        assert demands
        assert "SAMPLE" in note.upper()
        for d in demands:
            name = d.get("buyerName", "")
            assert name.startswith("Sample Buyer"), name
        blob = json.dumps(demands)
        for real_or_invented in ("BigBasket", "Sahyadri", "MahaFresh", "Deccan Agri"):
            assert real_or_invented not in blob


# ---------------------------------------------------------------------------
# 11. farmer-initiated offers (Make Offer)
# ---------------------------------------------------------------------------

class TestFarmerOffers:
    """A farmer offers one of their own lots against an open buyer requirement."""

    def _buyer(self, client):
        import uuid
        s = uuid.uuid4().hex[:10]
        res = client.post("/api/auth/register", json={
            "name": "Offer Buyer", "username": f"ob_{s}",
            "phone": "7" + s[:9].translate(str.maketrans("abcdef", "123456")),
            "password": "StrongPass!234", "role": "BUYER",
            "district": "Pune", "state": "Maharashtra",
        })
        assert res.status_code in (200, 201), res.get_json()
        return {"Authorization": f"Bearer {res.get_json()['token']}"}

    def _requirement(self, client, headers, commodity="Onion"):
        res = client.post("/api/buyer-requirements", headers=headers, json={
            "commodity": commodity, "quantity_qtl_min": 20,
            "grade": "Grade A", "price_per_qtl": 2050,
            "preferred_district": "Pune", "valid_until": "2026-12-01",
        })
        assert res.status_code in (200, 201), res.get_json()
        body = res.get_json()
        return body.get("requirement_id") or (body.get("requirement") or {}).get("id")

    def _lot(self, client, headers, commodity="Onion"):
        res = client.post("/api/lots", headers=headers, json={
            "commodity": commodity, "quantity_qtl": 25, "grade": "Grade A",
            "location": "Nashik, Maharashtra", "district": "Nashik",
            "state": "Maharashtra", "price_per_qtl": 1943.27,
        })
        assert res.status_code == 201, res.get_json()
        return res.get_json()["lot"]["id"]

    def test_farmer_offer_is_created_and_attributed(self, client, auth_headers):
        buyer = self._buyer(client)
        req_id = self._requirement(client, buyer)
        lot_id = self._lot(client, auth_headers)

        res = client.post("/api/offers", headers=auth_headers, json={
            "requirement_id": req_id, "lot_id": lot_id,
            "quantity_qtl": 25, "price_per_qtl": 1943.27,
            "message": "Grade A, ready for pickup.",
        })
        assert res.status_code == 201, res.get_json()
        body = res.get_json()
        assert body["success"] is True
        assert body["initiated_by"] == "FARMER"
        assert body["offer_id"]

        mine = client.get("/api/offers/my", headers=auth_headers).get_json()
        offers = mine.get("offers") or []
        assert any(o["id"] == body["offer_id"] for o in offers)
        offer = [o for o in offers if o["id"] == body["offer_id"]][0]
        assert offer["initiated_by"] == "FARMER"
        assert offer["status"] == "PENDING"
        assert offer["price_per_qtl"] == pytest.approx(1943.27)

    def test_offer_requires_a_requirement(self, client, auth_headers):
        lot_id = self._lot(client, auth_headers)
        res = client.post("/api/offers", headers=auth_headers, json={"lot_id": lot_id})
        assert res.status_code == 400
        assert "requirement_id" in res.get_json()["error"]

    def test_offer_requires_a_lot(self, client, auth_headers):
        buyer = self._buyer(client)
        req_id = self._requirement(client, buyer)
        res = client.post("/api/offers", headers=auth_headers,
                          json={"requirement_id": req_id})
        assert res.status_code == 400
        assert "lot_id" in res.get_json()["error"]

    def test_farmer_cannot_offer_someone_elses_lot(self, client, auth_headers):
        import uuid
        buyer = self._buyer(client)
        req_id = self._requirement(client, buyer)
        lot_id = self._lot(client, auth_headers)

        s = uuid.uuid4().hex[:10]
        other = client.post("/api/auth/register", json={
            "name": "Other Farmer", "username": f"of_{s}",
            "phone": "8" + s[:9].translate(str.maketrans("abcdef", "123456")),
            "password": "StrongPass!234", "role": "FARMER",
            "district": "Nashik", "state": "Maharashtra",
        })
        other_headers = {"Authorization": f"Bearer {other.get_json()['token']}"}

        res = client.post("/api/offers", headers=other_headers, json={
            "requirement_id": req_id, "lot_id": lot_id,
            "quantity_qtl": 10, "price_per_qtl": 2000,
        })
        assert res.status_code == 403

    def test_unknown_requirement_is_rejected(self, client, auth_headers):
        lot_id = self._lot(client, auth_headers)
        res = client.post("/api/offers", headers=auth_headers, json={
            "requirement_id": 999999, "lot_id": lot_id,
            "quantity_qtl": 10, "price_per_qtl": 2000,
        })
        assert res.status_code == 404

    @pytest.mark.parametrize("price,qty", [(0, 10), (-5, 10), (2000, 0)])
    def test_non_positive_amounts_rejected(self, client, auth_headers, price, qty):
        buyer = self._buyer(client)
        req_id = self._requirement(client, buyer)
        lot_id = self._lot(client, auth_headers)
        res = client.post("/api/offers", headers=auth_headers, json={
            "requirement_id": req_id, "lot_id": lot_id,
            "quantity_qtl": qty, "price_per_qtl": price,
        })
        assert res.status_code == 400

    def test_anonymous_cannot_offer(self, client):
        assert client.post("/api/offers", json={"requirement_id": 1, "lot_id": 1}).status_code == 401


# ---------------------------------------------------------------------------
# 12. weather: local centroids, honest failures, no invented readings
# ---------------------------------------------------------------------------

class TestWeatherLocation:
    def test_known_district_needs_no_external_geocoder(self, client, monkeypatch):
        """
        Nashik is in the published centroid table, so the district lookup must
        not depend on the external geocoder being reachable.
        """
        import urllib.request

        def _no_network(*a, **k):
            raise OSError("network blocked")

        # app.py imports urllib inside the handler, so patch it at the source.
        monkeypatch.setattr(urllib.request, "urlopen", _no_network)
        res = client.get("/api/weather?district=Nashik&state=Maharashtra")
        body = res.get_json()
        # The forecast fetch still fails (no network), but it must fail *after*
        # resolving the district locally — never with a geocoding error.
        assert body["success"] is False
        assert "district" not in body.get("error", "").lower()
        assert "geocod" not in body.get("error", "").lower()

    def test_weather_requires_an_explicit_location(self, client):
        res = client.get("/api/weather")
        assert res.status_code == 400
        assert "not guessed" in res.get_json()["error"].lower()

    def test_bad_coordinates_rejected(self, client):
        assert client.get("/api/weather?lat=999&lon=73").status_code == 400

    def test_failure_never_invents_a_reading(self, client):
        # TESTING=True blocks outbound HTTP, so this always takes the fail path.
        body = client.get("/api/weather?lat=19.99&lon=73.79").get_json()
        if not body.get("success"):
            assert "current" not in body
            assert "forecast" not in body
            assert "temperature_c" not in json.dumps(body)


class TestCropQualityHonesty:
    """The grader may only speak when a real model actually ran."""

    def test_endpoint_exists_and_refuses_without_an_image(self, client):
        # The route is now backed by ml/quality_inference.py. With no file
        # attached the honest answer is a 400 naming the reason.
        res = client.post("/api/ml/quality-assessment", data={})
        assert res.status_code == 400
        assert res.get_json()["reason"] == "no_image"

    def test_unavailable_response_carries_no_grade(self, client):
        import io
        res = client.post(
            "/api/ml/quality-assessment",
            data={"crop": "Banana", "image": (io.BytesIO(b"x"), "x.jpg")},
            content_type="multipart/form-data",
        )
        body = res.get_json()
        assert body["success"] is False
        assert "label" not in body and "confidence" not in body


# ---------------------------------------------------------------------------
# 13. AGMARKNET day-first dates (the "today's record dated in the future" bug)
# ---------------------------------------------------------------------------

class TestMandiDateParsing:
    """
    data.gov.in sends DD/MM/YYYY. Parsed month-first, 12/09/2026 (12 September)
    became 9 December, so today's record landed in the future and the live feed
    could never match "today".
    """

    @pytest.mark.parametrize("raw,expected", [
        ("12/09/2026", "2026-09-12"),   # 12 September, not 9 December
        ("12-09-2026", "2026-09-12"),
        ("31/12/2025", "2025-12-31"),   # unambiguous day-first
        ("01/01/2020", "2020-01-01"),
        ("2026-09-12", "2026-09-12"),   # ISO must stay untouched
        ("2026-12-09", "2026-12-09"),
    ])
    def test_day_first_dates(self, raw, expected):
        from ml.ingest import parse_date
        assert str(parse_date(raw).date()) == expected

    def test_todays_official_row_is_marked_live(self, monkeypatch):
        """A row dated today in AGMARKNET's own format must come back LIVE."""
        import datetime
        import services.mandi_live as ml

        today = datetime.date.today()
        row = {
            "state": "Punjab", "district": "Sangrur", "market": "Ahmedgarh",
            "commodity": "Onion", "variety": "Other", "grade": "FAQ",
            "arrival_date": today.strftime("%d/%m/%Y"),
            "min_price": "1500", "max_price": "1900", "modal_price": "1700",
        }
        monkeypatch.setattr(config, "DATA_GOV_API_KEY", "k")
        monkeypatch.setattr(config, "DATA_GOV_RESOURCE_ID", "r")
        monkeypatch.setattr(ml, "_CACHE", {})

        class _R:
            def read(self): return json.dumps({"records": [row]}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(ml.urllib.request, "urlopen", lambda *a, **k: _R())
        out = ml.fetch_live_prices(commodity="Onion", state="Punjab",
                                   district="Sangrur", market="Ahmedgarh")
        assert out["success"] is True
        assert out["live"] is True
        assert out["label"] == "TODAY'S LIVE MANDI DATA"
        assert out["records"][0]["arrival_date"] == today.isoformat()
        assert out["records"][0]["is_today"] is True

    def test_yesterdays_row_is_not_live(self, monkeypatch):
        import datetime
        import services.mandi_live as ml

        y = datetime.date.today() - datetime.timedelta(days=1)
        row = {
            "state": "Punjab", "district": "Sangrur", "market": "Ahmedgarh",
            "commodity": "Onion", "arrival_date": y.strftime("%d/%m/%Y"),
            "min_price": "1500", "max_price": "1900", "modal_price": "1700",
        }
        monkeypatch.setattr(config, "DATA_GOV_API_KEY", "k")
        monkeypatch.setattr(config, "DATA_GOV_RESOURCE_ID", "r")
        monkeypatch.setattr(ml, "_CACHE", {})

        class _R:
            def read(self): return json.dumps({"records": [row]}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(ml.urllib.request, "urlopen", lambda *a, **k: _R())
        out = ml.fetch_live_prices(commodity="Onion", state="Punjab")
        assert out["live"] is False
        assert out["label"] == "LATEST AVAILABLE MANDI DATA"
        assert out["records"][0]["arrival_date"] == y.isoformat()

    def test_todays_row_sorts_first(self, monkeypatch):
        import datetime
        import services.mandi_live as ml

        today = datetime.date.today()
        old = today - datetime.timedelta(days=4)
        base = {"state": "Punjab", "district": "Sangrur", "market": "Ahmedgarh",
                "commodity": "Onion", "min_price": "1500", "max_price": "1900",
                "modal_price": "1700"}
        rows = [dict(base, arrival_date=old.strftime("%d/%m/%Y")),
                dict(base, arrival_date=today.strftime("%d/%m/%Y"))]
        monkeypatch.setattr(config, "DATA_GOV_API_KEY", "k")
        monkeypatch.setattr(config, "DATA_GOV_RESOURCE_ID", "r")
        monkeypatch.setattr(ml, "_CACHE", {})

        class _R:
            def read(self): return json.dumps({"records": rows}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(ml.urllib.request, "urlopen", lambda *a, **k: _R())
        out = ml.fetch_live_prices(commodity="Onion")
        assert out["live"] is True
        assert out["records"][0]["arrival_date"] == today.isoformat()

    def test_cached_live_verdict_expires_when_the_date_rolls_over(self, monkeypatch):
        """
        A cached payload carries a frozen is_today/live verdict. Served after
        midnight it would announce TODAY'S LIVE MANDI DATA over yesterday's
        row, so the cache must expire on the calendar date, not the TTL alone.
        """
        import datetime
        import services.mandi_live as ml

        today = datetime.date.today()
        row = {"state": "Punjab", "district": "Sangrur", "market": "Ahmedgarh",
               "commodity": "Onion", "arrival_date": today.strftime("%d/%m/%Y"),
               "min_price": "1500", "max_price": "1900", "modal_price": "1700"}
        monkeypatch.setattr(config, "DATA_GOV_API_KEY", "k")
        monkeypatch.setattr(config, "DATA_GOV_RESOURCE_ID", "r")
        monkeypatch.setattr(ml, "_CACHE", {})

        class _R:
            def read(self): return json.dumps({"records": [row]}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(ml.urllib.request, "urlopen", lambda *a, **k: _R())

        first = ml.fetch_live_prices(commodity="Onion")
        assert first["live"] is True and first["cached"] is False
        # Same query inside the TTL on the same day: the cache is used.
        again = ml.fetch_live_prices(commodity="Onion")
        assert again["cached"] is True and again["live"] is True

        # Now the clock passes midnight. The stored row is yesterday's.
        tomorrow = today + datetime.timedelta(days=1)

        class _FakeDate(datetime.date):
            @classmethod
            def today(cls):
                return tomorrow

        monkeypatch.setattr(ml, "date", _FakeDate)
        rolled = ml.fetch_live_prices(commodity="Onion")
        assert rolled["cached"] is False, "stale cache served across a date change"
        assert rolled["live"] is False, "yesterday's row still announced as LIVE"
        assert rolled["label"] == "LATEST AVAILABLE MANDI DATA"


# ---------------------------------------------------------------------------
# 14. crop quality inference — real model or an honest refusal
# ---------------------------------------------------------------------------

class TestQualityInference:
    def test_unsupported_crop_is_refused_cleanly(self):
        from ml import quality_inference as qi
        with pytest.raises(qi.QualityUnavailable) as e:
            qi.assess(b"\xff\xd8\xff", "Banana")
        assert e.value.reason in ("unsupported_crop", "model_missing")

    def test_missing_checkpoint_is_refused_cleanly(self):
        from ml import quality_inference as qi
        if "Tomato" in qi.supported_crops():
            pytest.skip("a real tomato checkpoint is installed")
        with pytest.raises(qi.QualityUnavailable) as e:
            qi.assess(b"\xff\xd8\xff", "Tomato")
        assert e.value.reason == "model_missing"

    def test_onion_never_resolves_to_a_model(self):
        """The four checkpoints cover four crops. Onion is not one of them."""
        from ml import quality_inference as qi
        for name in ("Onion", "Onion (Red)", "Banana", "Wheat", ""):
            assert qi.canonical_crop(name) is None
            assert qi.model_file_for(name) is None

    def test_aliases_resolve_to_the_four_trained_crops(self):
        from ml import quality_inference as qi
        assert qi.canonical_crop("tomato") == "Tomato"
        assert qi.canonical_crop("Tomato (Hybrid)") == "Tomato"
        assert qi.canonical_crop("aloo") == "Potato"
        assert qi.canonical_crop("Potato - Jyoti") == "Potato"
        assert qi.canonical_crop("mirchi") == "Chile Pepper"
        assert qi.canonical_crop("hari mirch") == "New Mexico Green Chile"
        assert set(qi.CROP_MODELS) == {
            "Tomato", "Potato", "Chile Pepper", "New Mexico Green Chile",
        }

    def test_supported_crops_lists_one_entry_per_checkpoint(self):
        from ml import quality_inference as qi
        crops = qi.supported_crops()
        assert len(crops) == len(set(crops))
        assert set(crops) <= set(qi.CROP_MODELS)

    def test_invalid_image_for_a_supported_crop_is_refused(self):
        """A real checkpoint must still refuse a file that is not an image."""
        from ml import quality_inference as qi
        if "Tomato" not in qi.supported_crops():
            pytest.skip("no tomato checkpoint installed")
        with pytest.raises(qi.QualityUnavailable) as e:
            qi.assess(b"this is definitely not a JPEG", "Tomato")
        assert e.value.reason == "invalid_image"

    def test_real_checkpoints_produce_a_real_prediction(self):
        """
        Run every installed checkpoint over a genuine decoded image and check
        the output is a real distribution over that model's own class list —
        no placeholder, no fabricated grade.
        """
        from ml import quality_inference as qi
        installed = qi.supported_crops()
        if not installed:
            pytest.skip("no quality checkpoints installed")
        pytest.importorskip("torch")
        pytest.importorskip("torchvision")
        from PIL import Image
        import io as _io

        buf = _io.BytesIO()
        Image.new("RGB", (300, 300), (170, 60, 45)).save(buf, format="JPEG")
        photo = buf.getvalue()

        for crop in installed:
            out = qi.assess(photo, crop)
            assert out["success"] is True
            assert out["crop_canonical"] == crop
            assert out["result_type"] == "condition"
            assert out["model"]["architecture"] == "mobilenet_v3_large"
            assert out["labels_known"] is True
            labels = [d["label"] for d in out["distribution"]]
            assert len(labels) == out["model"]["num_classes"]
            assert out["label"] in labels
            probs = [d["probability"] for d in out["distribution"]]
            assert all(0.0 <= p <= 1.0 for p in probs)
            assert abs(sum(probs) - 1.0) < 0.02
            assert out["confidence"] == max(probs)

    def test_each_checkpoint_reports_its_own_class_list(self):
        """Class names come from the checkpoints, never from a hardcoded list."""
        from ml import quality_inference as qi
        expected = {
            "Tomato": ["Damaged", "Old", "Ripe", "Unripe"],
            "Potato": ["Defective", "Good Condition"],
            "Chile Pepper": ["Damaged", "Dried", "Old", "Ripe", "Unripe"],
            "New Mexico Green Chile": ["Damaged", "Dried", "Old", "Ripe", "Unripe"],
        }
        for crop in qi.supported_crops():
            entry = qi.load_model(crop)
            assert entry["labels"] == expected[crop], crop
            assert entry["label_source"].startswith("checkpoint")

    def test_empty_image_is_refused(self):
        from ml import quality_inference as qi
        with pytest.raises(qi.QualityUnavailable) as e:
            qi.assess(b"", "Tomato")
        assert e.value.reason == "no_image"

    def test_status_endpoint_is_truthful(self, client):
        from ml import quality_inference as qi
        body = client.get("/api/ml/quality-status").get_json()
        assert body["success"] is True
        assert body["available"] is bool(qi.supported_crops())
        assert body["supported_crops"] == qi.supported_crops()

    def test_assessment_without_a_file_is_a_clean_400(self, client):
        res = client.post("/api/ml/quality-assessment", data={"crop": "Tomato"})
        assert res.status_code == 400
        assert res.get_json()["reason"] == "no_image"

    def test_no_endpoint_ever_returns_a_grade_without_a_model(self, client):
        """Whatever happens, an unavailable analysis must not carry a grade."""
        import io
        data = {"crop": "Tomato", "image": (io.BytesIO(b"not an image"), "x.jpg")}
        res = client.post("/api/ml/quality-assessment", data=data,
                          content_type="multipart/form-data")
        body = res.get_json()
        if not body.get("success"):
            assert "label" not in body
            assert "confidence" not in body


# ---------------------------------------------------------------------------
# 15. sale-lot crop photo
# ---------------------------------------------------------------------------

class TestSaleLotImage:
    _PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
            b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

    def _data_url(self, mime="image/png", raw=None):
        import base64
        return f"data:{mime};base64," + base64.b64encode(raw or self._PNG).decode()

    def test_lot_without_an_image_still_publishes(self, client, auth_headers):
        res = client.post("/api/lots", headers=auth_headers, json={
            "commodity": "Onion", "quantity_qtl": 10,
            "location": "Nashik, Maharashtra", "price_per_qtl": 1900,
        })
        assert res.status_code == 201
        assert not res.get_json()["lot"].get("image_file")

    def test_lot_with_an_image_stores_and_serves_it(self, client, auth_headers):
        res = client.post("/api/lots", headers=auth_headers, json={
            "commodity": "Onion", "quantity_qtl": 25,
            "location": "Nashik, Maharashtra", "price_per_qtl": 1950,
            "image_data_url": self._data_url(),
        })
        assert res.status_code == 201, res.get_json()
        lot = res.get_json()["lot"]
        assert lot["image_file"]
        # The stored name is generated server-side, never client-supplied.
        assert lot["image_file"].startswith("lot_")
        served = client.get(f"/api/lots/{lot['id']}/image")
        assert served.status_code == 200
        assert served.mimetype.startswith("image/")

    def test_non_image_payload_is_rejected(self, client, auth_headers):
        res = client.post("/api/lots", headers=auth_headers, json={
            "commodity": "Onion", "quantity_qtl": 5, "location": "Nashik",
            "image_data_url": self._data_url(mime="application/pdf"),
        })
        assert res.status_code == 400
        assert "JPG" in res.get_json()["error"]

    def test_malformed_data_url_is_rejected(self, client, auth_headers):
        res = client.post("/api/lots", headers=auth_headers, json={
            "commodity": "Onion", "quantity_qtl": 5, "location": "Nashik",
            "image_data_url": "totally-not-a-data-url",
        })
        assert res.status_code == 400

    def test_image_request_for_a_lot_without_one_is_404(self, client, auth_headers):
        res = client.post("/api/lots", headers=auth_headers, json={
            "commodity": "Onion", "quantity_qtl": 8, "location": "Nashik",
        })
        lot_id = res.get_json()["lot"]["id"]
        assert client.get(f"/api/lots/{lot_id}/image").status_code == 404

    def test_client_cannot_choose_the_stored_filename(self, client, auth_headers):
        """A traversal attempt in the mime/name must never reach the filesystem."""
        res = client.post("/api/lots", headers=auth_headers, json={
            "commodity": "Onion", "quantity_qtl": 5, "location": "Nashik",
            "image_data_url": self._data_url(),
        })
        name = res.get_json()["lot"]["image_file"]
        assert "/" not in name and "\\" not in name and ".." not in name
