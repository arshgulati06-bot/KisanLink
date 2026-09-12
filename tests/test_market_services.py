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
