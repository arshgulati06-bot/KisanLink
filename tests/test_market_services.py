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
        import backend.app as appmod

        def _no_network(*a, **k):
            raise OSError("network blocked")

        # Weather responses are cached process-wide for 10 minutes, which is
        # deliberate — but it means an earlier test that reached Open-Meteo for
        # Nashik would serve this one from cache. Start from empty so the
        # geocoding path is what is actually under test.
        appmod._WEATHER_CACHE.clear()
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


# ---------------------------------------------------------------------------
# 16. upload size limits — regression for the 2 MB global cap
# ---------------------------------------------------------------------------

class TestUploadSizeLimits:
    """
    Flask's MAX_CONTENT_LENGTH was set to INGEST_MAX_BYTES (2 MB), which is a
    whole-app cap. Every real phone photo is larger than that, so the quality
    endpoint returned 413 before it ever ran and the farmer was told photo
    grading was "not connected" while the models were loaded and working.
    Earlier tests missed it because their fixture images were a few hundred
    bytes.
    """

    @staticmethod
    def _jpeg(mb):
        """A real, decodable JPEG of roughly `mb` megabytes."""
        pytest.importorskip("PIL")
        from PIL import Image
        import io as _io
        import random
        side = 1500
        buf = _io.BytesIO()
        rnd = random.Random(7)
        img = Image.new("RGB", (side, side))
        img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                     for _ in range(side * side)])
        img.save(buf, format="JPEG", quality=97)
        data = buf.getvalue()
        assert len(data) > mb * 1024 * 1024, f"fixture only {len(data)} bytes"
        return data

    def test_global_cap_clears_the_photo_cap(self):
        from ml import config as mlc
        from ml import quality_inference as qi
        assert mlc.UPLOAD_MAX_BYTES > qi.MAX_IMAGE_BYTES, (
            "the whole-app cap must clear the largest legitimate photo")
        assert mlc.UPLOAD_MAX_BYTES > mlc.INGEST_MAX_BYTES

    def test_a_three_megabyte_photo_is_analysed_not_rejected(self, client):
        import io as _io
        from ml import quality_inference as qi
        if "Tomato" not in qi.supported_crops():
            pytest.skip("no tomato checkpoint installed")
        data = self._jpeg(2)
        res = client.post("/api/ml/quality-assessment",
                          data={"crop": "Tomato",
                                "image": (_io.BytesIO(data), "photo.jpg")},
                          content_type="multipart/form-data")
        assert res.status_code != 413, "the global cap rejected a normal photo again"
        assert res.status_code == 200, res.get_json()
        body = res.get_json()
        assert body["success"] is True
        assert body["label"] in [d["label"] for d in body["distribution"]]

    def test_ingest_keeps_its_own_two_megabyte_limit(self, client):
        import json as _json
        payload = _json.dumps({"records": [{"pad": "x" * 100} for _ in range(30000)]})
        assert len(payload) > 2 * 1024 * 1024
        res = client.post("/api/ingest/update", data=payload,
                          content_type="application/json")
        assert res.status_code == 413
        assert "2 MB" in res.get_json()["error"]

    def test_413_names_the_limit_and_carries_a_reason(self, client):
        """
        The old handler returned {"error": "Payload too large."} with no
        reason, and the frontend turned any such failure into
        "photo grading is not connected" — which was untrue.
        """
        import io as _io
        from ml import config as mlc
        oversized = b"\xff\xd8\xff" + b"0" * (mlc.UPLOAD_MAX_BYTES + 1024)
        res = client.post("/api/ml/quality-assessment",
                          data={"crop": "Tomato",
                                "image": (_io.BytesIO(oversized), "huge.jpg")},
                          content_type="multipart/form-data")
        assert res.status_code == 413
        body = res.get_json()
        assert body["reason"] == "payload_too_large"
        assert "MB" in body["error"]
        assert body["success"] is False


# ---------------------------------------------------------------------------
# 17. sale-lot photo hardening
# ---------------------------------------------------------------------------

class TestLotImageHardening:
    def test_a_real_photo_over_two_megabytes_round_trips(self, client, auth_headers):
        import base64
        raw = TestUploadSizeLimits._jpeg(2)
        url = "data:image/jpeg;base64," + base64.b64encode(raw).decode()
        res = client.post("/api/lots", headers=auth_headers, json={
            "commodity": "Onion", "quantity_qtl": 14,
            "location": "Nashik, Maharashtra", "price_per_qtl": 1980,
            "image_data_url": url,
        })
        assert res.status_code == 201, res.get_json()
        lot_id = res.get_json()["lot"]["id"]
        got = client.get(f"/api/lots/{lot_id}/image")
        assert got.status_code == 200
        assert got.data == raw

    def test_non_image_bytes_labelled_as_jpeg_are_rejected(self, client, auth_headers):
        """The data URL's MIME is client-supplied, so the bytes must be decoded."""
        pytest.importorskip("PIL")
        import base64
        fake = base64.b64encode(b"<html>not an image at all</html>").decode()
        res = client.post("/api/lots", headers=auth_headers, json={
            "commodity": "Onion", "quantity_qtl": 5,
            "location": "Nashik, Maharashtra", "price_per_qtl": 1900,
            "image_data_url": "data:image/jpeg;base64," + fake,
        })
        assert res.status_code == 400
        assert "not a readable image" in res.get_json()["error"].lower()

    def test_image_response_forbids_content_sniffing(self, client, auth_headers):
        import base64
        png = TestSaleLotImage._PNG
        res = client.post("/api/lots", headers=auth_headers, json={
            "commodity": "Onion", "quantity_qtl": 6,
            "location": "Nashik, Maharashtra", "price_per_qtl": 1910,
            "image_data_url": "data:image/png;base64," + base64.b64encode(png).decode(),
        })
        assert res.status_code == 201
        lot_id = res.get_json()["lot"]["id"]
        got = client.get(f"/api/lots/{lot_id}/image")
        assert got.headers.get("X-Content-Type-Options") == "nosniff"

    @pytest.mark.parametrize("lot_id", [0, 999999])
    def test_unknown_lot_ids_are_a_clean_404(self, client, lot_id):
        res = client.get(f"/api/lots/{lot_id}/image")
        assert res.status_code == 404
        assert "error" in res.get_json()


# ---------------------------------------------------------------------------
# 18. static frontend contract
# ---------------------------------------------------------------------------

class TestFrontendContract:
    PAGES = ["farmer.html", "buyer.html", "auth.html"]

    def _page(self, name):
        import os
        root = os.path.join(os.path.dirname(__file__), "..", "frontend")
        path = os.path.join(root, "pages", name)
        if not os.path.exists(path):
            pytest.skip(f"{name} not present")
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    @pytest.mark.parametrize("page", PAGES)
    def test_no_duplicate_dom_ids(self, page):
        """
        farmer.html had two buttons sharing id 'cqa-analyze-again-btn', so
        getElementById only ever bound the first and 'Try Again' on the
        "Analysis Failed" card did nothing — the farmer was stuck on the error.
        """
        import re
        from collections import Counter
        ids = re.findall(r'\sid="([^"]+)"', self._page(page))
        dupes = [i for i, n in Counter(ids).items() if n > 1]
        assert not dupes, f"{page} has duplicate ids: {dupes}"

    def test_error_card_has_its_own_retry_button(self):
        html = self._page("farmer.html")
        assert 'id="cqa-error-retry-btn"' in html
        assert 'id="cqa-analyze-again-btn"' in html

    def test_no_misleading_not_connected_copy_in_frontend_js(self):
        import glob, os
        root = os.path.join(os.path.dirname(__file__), "..", "frontend", "js")
        if not os.path.isdir(root):
            pytest.skip("frontend/js not present")
        offenders = []
        for path in glob.glob(os.path.join(root, "*.js")):
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if "not connected on this server" in text:
                offenders.append(os.path.basename(path))
        assert not offenders, (
            "these files still claim photo grading is not connected: "
            + ", ".join(offenders))


# ---------------------------------------------------------------------------
# 19. offer -> acceptance -> transaction
# ---------------------------------------------------------------------------

class TestOfferFlow:
    """
    The farmer's "Received Offers" panel read from localStorage, which was
    never populated, so a buyer's offer could not reach the farmer's screen at
    all; and Accept mutated localStorage and minted a client-side transaction
    id instead of calling the server. These cover the server side of the fix.
    """

    def _pair(self, client):
        import uuid
        out = []
        for role, name in (("FARMER", "Ravi Patil"), ("BUYER", "Sunrise Traders")):
            sfx = uuid.uuid4().hex[:10]
            res = client.post("/api/auth/register", json={
                "name": name, "username": f"{role.lower()}_{sfx}",
                "phone": "9" + sfx[:9].translate(str.maketrans("abcdef", "123456")),
                "password": "StrongPass!234", "role": role,
                "district": "Nashik", "state": "Maharashtra",
            })
            assert res.status_code == 201, res.get_json()
            out.append({"Authorization": "Bearer " + res.get_json()["token"]})
        return out[0], out[1]

    def _lot_and_offer(self, client, farmer, buyer, price=2550):
        res = client.post("/api/lots", headers=farmer, json={
            "commodity": "Tomato", "quantity_qtl": 18,
            "location": "Nashik, Maharashtra", "price_per_qtl": 2400, "grade": "Ripe",
        })
        assert res.status_code == 201, res.get_json()
        lot_id = res.get_json()["lot"]["id"]
        res = client.post("/api/offers", headers=buyer, json={
            "lot_id": lot_id, "price_per_qtl": price, "quantity_qtl": 18,
            "message": "Pickup Friday",
        })
        assert res.status_code == 201, res.get_json()
        return lot_id, res.get_json()["offer_id"]

    def test_offer_carries_the_counterparty_name_and_crop(self, client):
        """A card reading "Buyer #297 / Lot #159" tells the farmer nothing."""
        farmer, buyer = self._pair(client)
        self._lot_and_offer(client, farmer, buyer)
        rows = client.get("/api/offers/my", headers=farmer).get_json()["offers"]
        assert rows, "the farmer must see the offer on their own lot"
        row = rows[0]
        assert row["buyer_name"] == "Sunrise Traders"
        assert row["commodity"] == "Tomato"
        assert row["grade"] == "Ripe"
        assert row["price_per_qtl"] == 2550
        assert row["status"] == "PENDING"

    def test_accepting_creates_a_real_transaction_both_sides_can_see(self, client):
        farmer, buyer = self._pair(client)
        _, offer_id = self._lot_and_offer(client, farmer, buyer)
        res = client.post(f"/api/offers/{offer_id}/respond", headers=farmer,
                          json={"status": "ACCEPTED"})
        assert res.status_code == 200, res.get_json()
        assert res.get_json()["transaction"]["id"]

        for who, label in ((farmer, "farmer"), (buyer, "buyer")):
            txs = client.get("/api/transactions/my", headers=who).get_json()["transactions"]
            assert len(txs) == 1, f"{label} cannot see the transaction"
            assert txs[0]["commodity"] == "Tomato"
            assert txs[0]["gross_amount"] == 2550 * 18
            assert txs[0]["buyer_name"] == "Sunrise Traders"
            assert txs[0]["seller_name"] == "Ravi Patil"

    def test_accepting_twice_is_not_a_500(self, client):
        """The second accept used to blow up on the transaction insert."""
        farmer, buyer = self._pair(client)
        _, offer_id = self._lot_and_offer(client, farmer, buyer)
        first = client.post(f"/api/offers/{offer_id}/respond", headers=farmer,
                            json={"status": "ACCEPTED"})
        second = client.post(f"/api/offers/{offer_id}/respond", headers=farmer,
                             json={"status": "ACCEPTED"})
        assert second.status_code == 200, second.get_json()
        # ...and it must not create a duplicate transaction
        assert second.get_json()["transaction"]["id"] == first.get_json()["transaction"]["id"]
        txs = client.get("/api/transactions/my", headers=farmer).get_json()["transactions"]
        assert len(txs) == 1

    def test_responding_to_an_unknown_offer_is_a_404(self, client):
        """The bare UPDATE reported success for any id, so this answered 200."""
        farmer, _ = self._pair(client)
        res = client.post("/api/offers/999999/respond", headers=farmer,
                          json={"status": "ACCEPTED"})
        assert res.status_code == 404
        assert res.get_json()["success"] is False

    def test_rejecting_records_the_rejection(self, client):
        farmer, buyer = self._pair(client)
        _, offer_id = self._lot_and_offer(client, farmer, buyer)
        res = client.post(f"/api/offers/{offer_id}/respond", headers=farmer,
                          json={"status": "REJECTED"})
        assert res.status_code == 200
        rows = client.get("/api/offers/my", headers=buyer).get_json()["offers"]
        assert rows[0]["status"] == "REJECTED"
        assert not client.get("/api/transactions/my",
                              headers=farmer).get_json()["transactions"]

    def test_dashboard_js_does_not_mint_its_own_transaction_ids(self):
        """
        Accept used to build `TX-2026-050` in the browser and push it into
        localStorage — a transaction that existed nowhere else.
        """
        import os
        path = os.path.join(os.path.dirname(__file__), "..",
                            "frontend", "js", "dashboard.js")
        if not os.path.exists(path):
            pytest.skip("dashboard.js not present")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "`TX-${" not in src, "dashboard.js is fabricating transaction ids again"
        assert "/offers/" in src and "respond" in src, (
            "accept/reject must call /api/offers/<id>/respond")


# ---------------------------------------------------------------------------
# 20. startup, laziness and the render-blocking font link
# ---------------------------------------------------------------------------

class TestStartupAndLaziness:
    """
    The dashboard used to wait ~13s before running a single line of JavaScript,
    and the server loaded the whole mandi archive plus Chronos before opening
    its socket. Neither is needed to show the page, sign in, check weather or
    grade a photo.
    """

    PAGES = ["frontend/pages/farmer.html", "frontend/pages/buyer.html",
             "frontend/pages/auth.html", "frontend/index.html"]

    def _read(self, rel):
        import os
        path = os.path.join(os.path.dirname(__file__), "..", *rel.split("/"))
        if not os.path.exists(path):
            pytest.skip(f"{rel} not present")
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    @pytest.mark.parametrize("page", PAGES)
    def test_font_stylesheet_never_blocks_the_parser(self, page):
        """
        A render-blocking <link> to fonts.googleapis.com held DOMContentLoaded
        for ~13s when the CDN was unreachable — offline demo wifi, captive
        portal — freezing weather, quality and forecast alike.
        """
        import re
        html = self._read(page)
        for tag in re.findall(r"<link\b[^>]*fonts\.googleapis\.com/css2[^>]*>", html):
            if 'rel="preconnect"' in tag or "rel='preconnect'" in tag:
                continue
            in_noscript = f"<noscript><link rel=\"stylesheet\" href" in html and tag in html
            assert 'media="print"' in tag or in_noscript, (
                f"{page} still loads the font CSS render-blocking: {tag[:110]}")

    def test_chronos_is_not_loaded_during_create_app(self, monkeypatch):
        """Chronos must load on the first forecast, not at import/startup."""
        import backend.app as appmod
        calls = []
        monkeypatch.setattr(appmod, "load_model",
                            lambda *a, **k: calls.append(1) or "PIPE")
        application = appmod.create_app(load_real_data=False, load_chronos=True)
        assert calls == [], "Chronos was loaded during create_app()"
        assert application.extensions["kisanlink"]["pipeline"] is None

    def test_pipeline_loads_once_and_is_reused(self, monkeypatch):
        import backend.app as appmod
        calls = []

        def _fake():
            calls.append(1)
            return "PIPE"

        monkeypatch.setattr(appmod, "load_model", _fake)
        application = appmod.create_app(load_real_data=False, load_chronos=True)
        with application.app_context():
            assert appmod._pipeline() == "PIPE"
            assert appmod._pipeline() == "PIPE"
            assert appmod._pipeline() == "PIPE"
        assert calls == [1], f"Chronos loaded {len(calls)} times, expected once"

    def test_data_dependent_endpoints_answer_503_while_warming(self):
        """Not a hang and not a 500 — a reason the frontend can act on."""
        import backend.app as appmod
        application = appmod.create_app(load_real_data=False, load_chronos=False)
        application.config["TESTING"] = True
        application.extensions["kisanlink"]["data_pending"] = True
        c = application.test_client()
        res = c.get("/api/commodities")
        assert res.status_code == 503
        body = res.get_json()
        assert body["reason"] == "data_warming_up"
        assert body["success"] is False

    def test_data_status_reports_readiness(self):
        import backend.app as appmod
        application = appmod.create_app(dataframe=_frame(), load_real_data=False,
                                        load_chronos=False)
        application.config["TESTING"] = True
        body = application.test_client().get("/api/data-status").get_json()
        assert body["success"] is True
        assert body["ready"] is True
        assert body["records"] > 0
        assert body["commodities"] >= 1

    def test_reported_sources_reflect_the_filesystem(self):
        """The list used to be hard-coded and omitted the yearly workbooks."""
        import os
        import backend.app as appmod
        names = {s["name"] for s in appmod._describe_sources()}
        for path in config.HISTORICAL_SOURCES:
            assert os.path.basename(path) in names
        for src in appmod._describe_sources():
            assert src["present"] == os.path.exists(
                os.path.join(os.path.dirname(__file__), "..", "ml", "data", src["name"])
            ) or src["type"] == "incremental"


# ---------------------------------------------------------------------------
# 21. weather latency budget
# ---------------------------------------------------------------------------

class TestWeatherBudget:
    def test_upstream_budget_fits_inside_the_browser_abort(self):
        """
        The client aborts at 30s. Two 12s upstream attempts plus an 8s geocode
        exceeded that, so a slow first load was guaranteed to look like a
        failure. Keep the server's worst case comfortably under the client's.
        """
        import os
        import re
        path = os.path.join(os.path.dirname(__file__), "..", "backend", "app.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        wx = [int(t) for t in re.findall(r"urlopen\(wx_url, timeout=(\d+)\)", src)]
        geo = [int(t) for t in re.findall(r"urlopen\(geo_url, timeout=(\d+)\)", src)]
        assert wx and geo, "could not find the weather timeouts"
        worst = max(geo) + 2 * max(wx) + 1     # geocode + two attempts + backoff
        assert worst < 25, f"weather worst case {worst}s is too close to the 30s client abort"

    def test_weather_responses_are_cached(self):
        import backend.app as appmod
        appmod._WEATHER_CACHE.clear()
        assert appmod._weather_cache_get(19.99, 73.79) is None
        appmod._weather_cache_put(19.99, 73.79, b'{"current":{}}')
        assert appmod._weather_cache_get(19.99, 73.79) == b'{"current":{}}'
        # ~1 km bucketing: a nearby request reuses the entry
        assert appmod._weather_cache_get(19.9903, 73.7904) == b'{"current":{}}'
        appmod._WEATHER_CACHE.clear()

    def test_weather_cache_is_bounded(self):
        import backend.app as appmod
        appmod._WEATHER_CACHE.clear()
        for i in range(300):
            appmod._weather_cache_put(10 + i / 100.0, 70.0, b"x")
        assert len(appmod._WEATHER_CACHE) <= 256
        appmod._WEATHER_CACHE.clear()


# ---------------------------------------------------------------------------
# 22. the quality request can never hang the card
# ---------------------------------------------------------------------------

class TestQualityRequestRobustness:
    def _js(self, name):
        import os
        path = os.path.join(os.path.dirname(__file__), "..", "frontend", "js", name)
        if not os.path.exists(path):
            pytest.skip(f"{name} not present")
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_quality_fetch_is_bounded_by_an_abort(self):
        """A bare fetch() has no timeout: a stalled upload left the card on
        "Analysing Crop Quality…" with no way out."""
        src = self._js("api.js")
        i = src.index("async function assessCropQuality")
        body = src[i: src.index("async function", i + 10)]
        assert "AbortController" in body, "the quality fetch has no abort controller"
        assert "signal: controller.signal" in body, "the abort signal is not passed to fetch"
        assert "AbortError" in body, "an abort is not reported as a timeout"

    def test_a_non_json_reply_is_not_treated_as_success(self):
        src = self._js("api.js")
        assert "bad_response" in src

    def test_the_analyse_handler_always_clears_loading_and_reenables(self):
        src = self._js("crop-quality.js")
        i = src.index("function _onAnalyzeClick")
        body = src[i: i + 2200]
        assert "btn.disabled = false" in body, "the button can stay stuck disabled"
        assert "loadingState" in body, "the spinner is not guaranteed to clear"

    def test_render_errors_do_not_masquerade_as_analysis_failure(self):
        """A throw while painting used to land in the request's .catch()."""
        src = self._js("crop-quality.js")
        i = src.index("function _onAnalyzeClick")
        body = src[i: i + 2200]
        assert "renderErr" in body


# ---------------------------------------------------------------------------
# 23. the hidden attribute must actually hide
# ---------------------------------------------------------------------------

class TestHiddenAttributeWins:
    """
    `[hidden] { display: none }` in the UA stylesheet has specificity 0,0,1, so
    any class rule setting `display` defeats `element.hidden = true`. That is
    how the crop-quality spinner stayed on screen beside a finished result:
    `.cqa-loading-state { display: flex }` outranked the attribute.
    """

    def _css(self):
        import glob, os
        root = os.path.join(os.path.dirname(__file__), "..", "frontend", "css")
        if not os.path.isdir(root):
            pytest.skip("frontend/css not present")
        out = {}
        for path in glob.glob(os.path.join(root, "*.css")):
            with open(path, encoding="utf-8") as fh:
                out[os.path.basename(path)] = fh.read()
        return out

    def test_a_global_hidden_rule_exists(self):
        import re
        joined = "\n".join(self._css().values())
        assert re.search(r"\[hidden\]\s*\{[^}]*display\s*:\s*none\s*!important",
                         joined), (
            "no global [hidden] rule: element.hidden can be defeated by any "
            "class that sets display")

    def test_the_rule_is_in_the_first_stylesheet(self):
        """It must load before the sheets whose classes it has to outrank."""
        import os, re
        page = os.path.join(os.path.dirname(__file__), "..",
                            "frontend", "pages", "farmer.html")
        if not os.path.exists(page):
            pytest.skip("farmer.html not present")
        with open(page, encoding="utf-8") as fh:
            order = re.findall(r'href="\.\./css/([a-z-]+\.css)"', fh.read())
        css = self._css()
        first_with_rule = next(
            (name for name in order
             if re.search(r"\[hidden\]\s*\{[^}]*display\s*:\s*none\s*!important",
                          css.get(name, ""))),
            None)
        assert first_with_rule == order[0], (
            f"the [hidden] rule should be in {order[0]}, found in {first_with_rule}")

    @pytest.mark.parametrize("cls", [
        "cqa-loading-state", "cqa-idle-state", "cqa-error-state", "pf-state-box",
    ])
    def test_state_boxes_are_covered(self, cls):
        """These are the state machines that toggle purely via .hidden."""
        import re
        joined = "\n".join(self._css().values())
        assert re.search(r"\." + re.escape(cls) + r"\s*\{[^}]*display", joined), (
            f".{cls} no longer sets display — update this test")
        # covered either by its own [hidden] rule or the global one
        assert (re.search(r"\." + re.escape(cls) + r"\[hidden\]", joined)
                or re.search(r"\[hidden\]\s*\{[^}]*display\s*:\s*none\s*!important",
                             joined))


# ---------------------------------------------------------------------------
# 24. Chronos picks the newest usable series, and the UI says whose it is
# ---------------------------------------------------------------------------

class TestForecastSeriesHonesty:
    def test_newer_observations_are_never_dropped_for_older_ones(self):
        """
        Rule 3: never silently fall back to older data when newer valid data
        exists for the same series.
        """
        import numpy as np
        from ml.data_loader import _truncate_at_gap

        old_dates = pd.date_range("2022-02-05", "2023-02-25", freq="3D")
        for newer_n in (40, 200):
            new_dates = pd.date_range("2026-01-01", periods=newer_n, freq="D")
            dates = old_dates.append(new_dates)
            prices = np.concatenate([np.full(len(old_dates), 2000.0),
                                     np.full(newer_n, 3000.0)])
            _p, d, info = _truncate_at_gap(prices, dates, config.MAX_GAP_DAYS, 30)
            assert d[-1].year == 2026, (
                f"a {newer_n}-observation 2026 segment was discarded for older data")
            assert info and "2026-01-01" in info

    def test_a_short_newer_segment_is_kept_not_discarded(self):
        """
        With too few post-gap points to stand alone, the full series is kept —
        the newer observations are still present, never thrown away.
        """
        import numpy as np
        from ml.data_loader import _truncate_at_gap

        old_dates = pd.date_range("2022-02-05", "2023-02-25", freq="3D")
        new_dates = pd.date_range("2026-01-01", periods=5, freq="D")
        dates = old_dates.append(new_dates)
        prices = np.concatenate([np.full(len(old_dates), 2000.0), np.full(5, 3000.0)])
        _p, d, info = _truncate_at_gap(prices, dates, config.MAX_GAP_DAYS, 30)
        assert d[-1].year == 2026, "newer observations were dropped"
        assert info and "fewer than" in info, "the fallback must explain itself"

    def test_forecast_reports_both_the_series_and_dataset_end_dates(self, client):
        """
        A market whose history stops in 2023 read as though the whole archive
        stopped in 2023, contradicting the dataset figure on the dashboard.
        """
        res = client.post("/api/forecast", json={
            "commodity": "Onion", "state": "Maharashtra",
            "district": "Nashik", "market": "Pimpalgaon", "days": 7,
        })
        if res.status_code != 200 or not res.get_json().get("success"):
            pytest.skip("fixture frame has no forecastable Pimpalgaon series")
        body = res.get_json()
        assert "dataset_latest_date" in body
        assert "series_is_behind_dataset" in body
        assert isinstance(body["series_is_behind_dataset"], bool)
        assert body["date_range"]["end"] == body["latest_actual_date"]

    def test_forecast_ui_attributes_the_range_to_the_market(self):
        import os
        path = os.path.join(os.path.dirname(__file__), "..",
                            "frontend", "js", "price-forecast.js")
        if not os.path.exists(path):
            pytest.skip("price-forecast.js not present")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "Data available for" in src, "the range is still labelled generically"
        assert "series_is_behind_dataset" in src, (
            "the UI does not explain a market whose history ends early")
        assert "Date range: '" not in src, "the ambiguous label is still present"


# ---------------------------------------------------------------------------
# 25. condition -> marketplace grade mapping
# ---------------------------------------------------------------------------

class TestQualityGradeMapping:
    """
    The app speaks Grade A/B/C everywhere (schema, the Create Sale Lot form,
    ml/buyer_matcher) but nothing mapped a model condition onto it, so the card
    could only show a raw class like "Unripe".
    """

    def test_every_class_of_every_checkpoint_is_mapped(self):
        from ml import quality_inference as qi
        installed = qi.supported_crops()
        if not installed:
            pytest.skip("no quality checkpoints installed")
        unmapped = []
        for crop in installed:
            for label in qi.load_model(crop)["labels"]:
                if qi.grade_for(label)[0] is None:
                    unmapped.append((crop, label))
        assert not unmapped, f"classes with no grade: {unmapped}"

    @pytest.mark.parametrize("condition,expected", [
        ("Ripe", "Grade A"), ("Good Condition", "Grade A"),
        ("Unripe", "Grade B"), ("Old", "Grade B"), ("Dried", "Grade B"),
        ("Damaged", "Grade C"), ("Defective", "Grade C"),
    ])
    def test_mapping_is_the_documented_one(self, condition, expected):
        from ml import quality_inference as qi
        grade, basis = qi.grade_for(condition)
        assert grade == expected
        assert condition.lower() in basis.lower()

    def test_mapping_is_deterministic_and_case_insensitive(self):
        from ml import quality_inference as qi
        for spelling in ("Ripe", "ripe", "  RIPE  ", "good_condition"):
            first = qi.grade_for(spelling)[0]
            assert first == qi.grade_for(spelling)[0]
        assert qi.grade_for("good_condition")[0] == "Grade A"

    def test_an_unknown_condition_gets_no_invented_grade(self):
        from ml import quality_inference as qi
        grade, basis = qi.grade_for("Sunscalded")
        assert grade is None
        assert "manually" in basis.lower()

    def test_assess_returns_grade_alongside_the_untouched_condition(self):
        from ml import quality_inference as qi
        if "Potato" not in qi.supported_crops():
            pytest.skip("no potato checkpoint")
        pytest.importorskip("torch")
        from PIL import Image
        import io as _io
        buf = _io.BytesIO()
        Image.new("RGB", (256, 256), (166, 124, 74)).save(buf, format="JPEG")
        out = qi.assess(buf.getvalue(), "Potato")
        assert out["label"] in [d["label"] for d in out["distribution"]]
        assert out["quality_grade"] == qi.grade_for(out["label"])[0]
        assert out["grade_basis"]
        assert isinstance(out["grade_is_low_confidence"], bool)
        # the condition must never be rewritten to suit the grade
        assert out["label"] == out["distribution"][out["class_index"]]["label"]

    def test_low_confidence_is_flagged_but_never_changes_the_grade(self):
        from ml import quality_inference as qi
        assert qi.GRADE_CONFIDENCE_FLOOR == 0.60
        # the flag is derived from the top probability only
        assert qi.grade_for("Ripe")[0] == "Grade A"

    def test_grades_match_the_vocabulary_the_rest_of_the_app_uses(self):
        """Lot creation defaults and the buyer matcher speak Grade A/B/C."""
        from ml import quality_inference as qi
        assert set(qi.CONDITION_GRADE.values()) <= {"Grade A", "Grade B", "Grade C"}

    def test_frontend_shows_grade_and_condition_together(self):
        import os
        path = os.path.join(os.path.dirname(__file__), "..",
                            "frontend", "js", "crop-quality.js")
        if not os.path.exists(path):
            pytest.skip("crop-quality.js not present")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "qualityGrade" in src
        assert "Condition:" in src


# ---------------------------------------------------------------------------
# 26. weather robustness
# ---------------------------------------------------------------------------

class TestWeatherRobustness:
    def test_a_failed_fetch_is_never_cached_as_success(self, client, monkeypatch):
        import urllib.request
        import backend.app as appmod
        appmod._WEATHER_CACHE.clear()

        def _boom(*a, **k):
            raise OSError("network blocked")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        res = client.get("/api/weather?district=Nashik&state=Maharashtra")
        assert res.get_json()["success"] is False
        assert not appmod._WEATHER_CACHE, "a failure poisoned the cache"

    def test_the_failure_names_the_cause(self, client, monkeypatch):
        """DNS, a firewall and a timeout need different actions — say which."""
        import socket
        import urllib.request
        import backend.app as appmod
        appmod._WEATHER_CACHE.clear()

        # Under TESTING external HTTP is deliberately disabled, which
        # short-circuits to its own reason. Allow it so the classification
        # branch under test actually runs.
        monkeypatch.setattr(appmod, "_allow_external_http", lambda: True)

        cases = {
            socket.timeout("timed out"): "provider_timeout",
            urllib.error.URLError(socket.gaierror("no dns")): "dns_failure",
            OSError("refused"): "provider_unreachable",
        }
        for exc, expected in cases.items():
            appmod._WEATHER_CACHE.clear()
            monkeypatch.setattr(urllib.request, "urlopen",
                                lambda *a, _e=exc, **k: (_ for _ in ()).throw(_e))
            body = client.get("/api/weather?district=Nashik&state=Maharashtra").get_json()
            assert body["success"] is False
            assert body.get("reason") == expected, (exc, body.get("reason"))
            assert body.get("provider") == "api.open-meteo.com"
            # never a fabricated reading
            assert "current" not in body or not body.get("current")

    def test_a_cache_hit_does_not_extend_its_own_ttl(self, monkeypatch):
        """
        Re-storing on every hit pushed the timestamp forward, so a busy
        location's weather would never expire and never refresh.
        """
        import time as _time
        import backend.app as appmod
        appmod._WEATHER_CACHE.clear()
        appmod._weather_cache_put(19.99, 73.79, b"body")
        first_ts = list(appmod._WEATHER_CACHE.values())[0][0]
        _time.sleep(0.05)
        appmod._weather_cache_get(19.99, 73.79)
        assert list(appmod._WEATHER_CACHE.values())[0][0] == first_ts
        appmod._WEATHER_CACHE.clear()

    def test_cache_keys_distinguish_locations(self):
        import backend.app as appmod
        appmod._WEATHER_CACHE.clear()
        appmod._weather_cache_put(19.99, 73.79, b"nashik")
        appmod._weather_cache_put(28.61, 77.21, b"delhi")
        assert appmod._weather_cache_get(19.99, 73.79) == b"nashik"
        assert appmod._weather_cache_get(28.61, 77.21) == b"delhi"
        assert appmod._weather_cache_get(12.97, 77.59) is None
        appmod._WEATHER_CACHE.clear()

    def test_weather_failure_does_not_disturb_other_endpoints(self, client, monkeypatch):
        """Rule 14: weather must never take the rest of the app down."""
        import urllib.request
        import backend.app as appmod
        appmod._WEATHER_CACHE.clear()
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
        assert client.get("/api/weather?district=Nashik&state=Maharashtra")\
                     .get_json()["success"] is False
        assert client.get("/api/ml/quality-status").status_code == 200
        assert client.get("/api/commodities").status_code in (200, 503)
        assert client.get("/api/data-status").status_code == 200

    def test_retry_never_replays_an_unusable_query(self):
        """An empty first query was stored and replayed forever."""
        import os
        path = os.path.join(os.path.dirname(__file__), "..",
                            "frontend", "js", "weather-strip.js")
        if not os.path.exists(path):
            pytest.skip("weather-strip.js not present")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "LAST_QUERY = opts || {}" not in src, "the poisoning assignment is back"
        assert "if (hasLocation(opts)) LAST_QUERY = opts;" in src
        assert "function bestLocation" in src, "retry must re-resolve the location"

    def test_auto_load_and_retry_share_one_pipeline(self):
        import os, re
        path = os.path.join(os.path.dirname(__file__), "..",
                            "frontend", "js", "weather-strip.js")
        if not os.path.exists(path):
            pytest.skip("weather-strip.js not present")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        # both init() and the retry button resolve through bestLocation()
        assert len(re.findall(r"bestLocation\(\)", src)) >= 2


# ---------------------------------------------------------------------------
# 27. forecast uses the selected market's own real series
# ---------------------------------------------------------------------------

class TestForecastUsesSelectedMarket:
    def test_response_separates_all_four_dates(self, client):
        res = client.post("/api/forecast", json={
            "commodity": "Onion", "state": "Maharashtra",
            "district": "Nashik", "market": "Pimpalgaon", "days": 7,
        })
        if res.status_code != 200 or not res.get_json().get("success"):
            pytest.skip("fixture frame has no forecastable Pimpalgaon series")
        b = res.get_json()
        for key in ("latest_actual_date", "dataset_latest_date",
                    "context_range", "forecast_starts"):
            assert key in b, f"missing {key}"
        assert b["date_range"]["end"] == b["latest_actual_date"]
        # the forecast must begin AFTER this market's last real observation
        assert b["forecast_starts"] > b["latest_actual_date"]
        if b["context_range"]:
            assert b["context_range"]["end"] == b["latest_actual_date"]

    def test_ui_renders_all_four_dates(self):
        import os
        path = os.path.join(os.path.dirname(__file__), "..",
                            "frontend", "js", "price-forecast.js")
        if not os.path.exists(path):
            pytest.skip("price-forecast.js not present")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for phrase in ("Data available for", "Series fed to Chronos",
                       "Forecast starts", "Whole archive runs to"):
            assert phrase in src, f"the UI never shows: {phrase}"


# ---------------------------------------------------------------------------
# 28. assistant: real answers, Hindi/Hinglish, no placeholder
# ---------------------------------------------------------------------------

class TestAssistant:
    """
    The widget used to reply "Assistant backend not connected. Responses are
    placeholder only." after a fake 900ms pause. There is now a real endpoint
    answering from the loaded archive, the quality models and the farmer's own
    lots and offers.
    """

    @pytest.mark.parametrize("text,intent", [
        ("bhai tomato ka bhav kya hai?", "price"),
        ("mere tamatar ka kya bhaav hai?", "price"),
        ("\u092e\u0947\u0930\u0947 \u091f\u092e\u093e\u091f\u0930 \u0915\u093e \u092d\u093e\u0935 \u0915\u094d\u092f\u093e \u0939\u0948", "price"),
        ("mujhe kahan bechna chahiye?", "best_market"),
        ("best mandi kaunsi hai?", "best_market"),
        ("sell now karu?", "sell_or_wait"),
        ("kab bechu?", "sell_or_wait"),
        ("forecast kya bol raha hai?", "forecast"),
        ("mera crop kaisa hai?", "quality"),
        ("grade kya hai?", "quality"),
        ("mere buyers kaun hain?", "buyers"),
        ("what is the weather", "weather"),
    ])
    def test_intents_from_english_hindi_and_hinglish(self, text, intent):
        from services import assistant as asst
        assert asst.detect_intent(text) == intent

    @pytest.mark.parametrize("text,crop", [
        ("tomato ka bhav", "Tomato"), ("tamatar ka rate", "Tomato"),
        ("\u091f\u092e\u093e\u091f\u0930", "Tomato"),
        ("pyaz kaisa hai", "Onion"), ("aloo ka daam", "Potato"),
        ("gehu ka bhav", "Wheat"), ("nothing here", None),
    ])
    def test_crop_extraction(self, text, crop):
        from services import assistant as asst
        assert asst.detect_crop(text) == crop

    def test_language_detection(self):
        from services import assistant as asst
        assert asst.detect_language("\u092e\u0947\u0930\u0947 \u091f\u092e\u093e\u091f\u0930") == "hi"
        assert asst.detect_language("bhai mera tamatar kaisa hai") == "hi"
        assert asst.detect_language("what is the price of tomato") == "en"

    def test_endpoint_answers_a_price_question_from_real_data(self, client):
        res = client.post("/api/assistant/message",
                          json={"message": "onion ka bhav kya hai", "lang": "en"})
        assert res.status_code == 200
        body = res.get_json()
        assert body["success"] is True
        assert body["intent"] == "price"
        assert body["crop"] == "Onion"
        assert body["engine"] == "kisanlink-rules"
        # never the old placeholder
        assert "placeholder" not in body["reply"].lower()
        assert "not connected" not in body["reply"].lower()

    def test_reply_language_follows_the_selection(self, client):
        import re
        hi = client.post("/api/assistant/message",
                         json={"message": "help", "lang": "hi"}).get_json()
        en = client.post("/api/assistant/message",
                         json={"message": "help", "lang": "en"}).get_json()
        assert re.search(r"[\u0900-\u097F]", hi["reply"]), "Hindi selection did not yield Devanagari"
        assert not re.search(r"[\u0900-\u097F]", en["reply"])

    def test_an_unsupported_locale_falls_back_to_english_not_gibberish(self, client):
        import re
        body = client.post("/api/assistant/message",
                           json={"message": "help", "lang": "ta"}).get_json()
        assert body["lang"] == "en"
        assert not re.search(r"[\u0900-\u097F]", body["reply"])

    def test_quality_question_uses_the_dashboard_state(self, client):
        body = client.post("/api/assistant/message", json={
            "message": "meri quality kaisi hai", "lang": "en",
            "quality": {"crop": "Tomato", "grade": "Grade C",
                        "condition": "Damaged", "confidence": 0.6782,
                        "low_confidence": False},
        }).get_json()
        assert "Grade C" in body["reply"]
        assert "Damaged" in body["reply"]
        assert "68" in body["reply"]

    def test_low_confidence_is_passed_on_to_the_farmer(self, client):
        body = client.post("/api/assistant/message", json={
            "message": "grade kya hai", "lang": "en",
            "quality": {"crop": "Chile Pepper", "grade": "Grade B",
                        "condition": "Dried", "confidence": 0.29,
                        "low_confidence": True},
        }).get_json()
        assert "low" in body["reply"].lower()

    def test_without_a_quality_check_it_says_so_and_names_the_trained_crops(self, client):
        from ml import quality_inference as qi
        body = client.post("/api/assistant/message",
                           json={"message": "quality kya hai", "lang": "en"}).get_json()
        assert "not run" in body["reply"].lower() or "photo" in body["reply"].lower()
        if qi.supported_crops():
            assert qi.supported_crops()[0] in body["reply"]

    def test_an_unknown_crop_is_not_answered_with_an_invented_price(self, client):
        body = client.post("/api/assistant/message",
                           json={"message": "dragonfruit ka bhav", "lang": "en"}).get_json()
        assert "\u20b9" not in body["reply"], "a price was invented for an unmatched crop"

    def test_empty_message_is_rejected(self, client):
        res = client.post("/api/assistant/message", json={"message": "   "})
        assert res.status_code == 400

    def test_a_very_long_message_does_not_break_it(self, client):
        res = client.post("/api/assistant/message",
                          json={"message": "tomato ka bhav " * 500})
        assert res.status_code == 200

    def test_frontend_no_longer_ships_the_placeholder(self):
        import os
        path = os.path.join(os.path.dirname(__file__), "..",
                            "frontend", "js", "chat-assistant.js")
        if not os.path.exists(path):
            pytest.skip("chat-assistant.js not present")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "not yet connected to a live AI model" not in src
        assert "/assistant/message" in src, "the widget does not call the real endpoint"
        assert "AbortController" in src, "the assistant call is unbounded"


# ---------------------------------------------------------------------------
# 29. Sell Now carries the photo assessment into the lot
# ---------------------------------------------------------------------------

class TestSellNowPrefill:
    def test_the_assessed_grade_is_prefilled_not_defaulted(self):
        """
        The lot published as "Grade A" no matter what the model said, so the
        buyer saw a grade nobody had assessed.
        """
        import os
        path = os.path.join(os.path.dirname(__file__), "..",
                            "frontend", "js", "step4-farmer.js")
        if not os.path.exists(path):
            pytest.skip("step4-farmer.js not present")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "assessedGrade" in src, "the photo grade never reaches the lot form"
        assert "lot-grade" in src
        assert "assessedCondition" in src

    def test_a_lot_can_be_published_with_each_grade(self, client, auth_headers):
        """Whatever the model concludes must be publishable end to end."""
        for grade in ("Grade A", "Grade B", "Grade C"):
            res = client.post("/api/lots", headers=auth_headers, json={
                "commodity": "Tomato", "quantity_qtl": 12,
                "location": "Nashik, Maharashtra", "price_per_qtl": 2400,
                "grade": grade,
            })
            assert res.status_code == 201, res.get_json()
            assert res.get_json()["lot"]["grade"] == grade


# ---------------------------------------------------------------------------
# 30. inference-pipeline invariants behind the reported confidence
# ---------------------------------------------------------------------------

class TestInferencePipelineIsSound:
    """
    Guards the things that would silently corrupt confidence if they regressed.
    Investigated because reported confidence looked low: the pipeline turned
    out to be correct, so the number is real and must not be massaged.
    """

    def _entry(self):
        from ml import quality_inference as qi
        if "Tomato" not in qi.supported_crops():
            pytest.skip("no tomato checkpoint")
        pytest.importorskip("torch")
        return qi, qi.load_model("Tomato")

    def test_model_is_in_eval_mode(self):
        """Train-mode BatchNorm/Dropout would make every prediction noise."""
        import torch
        _qi, entry = self._entry()
        net = entry["model"]
        assert net.training is False
        assert not [m for m in net.modules()
                    if isinstance(m, (torch.nn.BatchNorm2d, torch.nn.Dropout)) and m.training]

    def test_class_count_matches_the_classifier_head(self):
        _qi, entry = self._entry()
        assert entry["model"].classifier[3].out_features == len(entry["labels"])
        assert entry["label_source"].startswith("checkpoint")

    def test_transform_is_resize_crop_totensor_normalize_in_that_order(self):
        qi, entry = self._entry()
        chain = [type(t).__name__ for t in qi._transform(entry["preprocess"]).transforms]
        assert chain == ["Resize", "CenterCrop", "ToTensor", "Normalize"]

    def test_tensor_shape_and_channel_order(self):
        import io as _io
        from PIL import Image
        qi, entry = self._entry()
        buf = _io.BytesIO()
        Image.new("RGB", (300, 300), (200, 30, 30)).save(buf, format="JPEG")
        img = Image.open(_io.BytesIO(buf.getvalue())).convert("RGB")
        x = qi._transform(entry["preprocess"])(img).unsqueeze(0)
        assert tuple(x.shape) == (1, 3, 224, 224)
        # a red image must have the highest signal in channel 0 (RGB, not BGR)
        means = [float(x[0, c].mean()) for c in range(3)]
        assert means[0] == max(means), f"channels look swapped: {means}"

    def test_probabilities_are_a_real_distribution(self):
        import io as _io
        from PIL import Image
        qi, _entry = self._entry()
        buf = _io.BytesIO()
        Image.new("RGB", (300, 300), (200, 30, 30)).save(buf, format="JPEG")
        out = qi.assess(buf.getvalue(), "Tomato")
        probs = [d["probability"] for d in out["distribution"]]
        assert abs(sum(probs) - 1.0) < 0.01
        assert all(0.0 <= p <= 1.0 for p in probs)
        assert out["confidence"] == max(probs)

    def test_inference_is_deterministic(self):
        """Any augmentation leaking into inference would show up here."""
        import io as _io
        from PIL import Image
        qi, _entry = self._entry()
        buf = _io.BytesIO()
        Image.new("RGB", (300, 300), (200, 30, 30)).save(buf, format="JPEG")
        data = buf.getvalue()
        runs = [qi.assess(data, "Tomato") for _ in range(3)]
        assert len({r["label"] for r in runs}) == 1
        assert len({round(r["confidence"], 6) for r in runs}) == 1

    def test_confidence_is_never_rescaled_or_clamped(self):
        """
        The reported number must be the raw softmax maximum. Nothing may
        multiply, offset or floor it to make the UI look better.
        """
        import inspect
        from ml import quality_inference as qi
        src = inspect.getsource(qi.assess)
        assert 'round(values[top], 4)' in src, "confidence is no longer the raw max"
        for bad in ("* 1.", "+ 0.1", "max(0.9", "min(1.0, values"):
            assert bad not in src, f"confidence looks massaged: {bad}"


# ---------------------------------------------------------------------------
# 31. live mandi diagnostics — the cases that were being conflated
# ---------------------------------------------------------------------------

class TestLiveMandiDiagnostics:
    """
    "Official API configured" only ever meant the key string was non-empty, so
    the dashboard could claim the feed was configured while every price shown
    was historical. These cover the distinct causes.
    """

    TODAY = None

    def _row(self, day):
        return {"state": "Punjab", "district": "Sangrur", "market": "Ahmedgarh",
                "commodity": "Tomato", "arrival_date": day.strftime("%d/%m/%Y"),
                "min_price": "2600", "max_price": "3100", "modal_price": "2850"}

    def _stub(self, rows):
        class _R:
            status = 200
            def read(_s): return json.dumps({"records": rows}).encode()
            def __enter__(_s): return _s
            def __exit__(_s, *a): return False
        return lambda *a, **k: _R()

    def _diagnose(self, monkeypatch, urlopen, key="k", res="r"):
        import services.mandi_live as ml
        monkeypatch.setattr(config, "DATA_GOV_API_KEY", key)
        monkeypatch.setattr(config, "DATA_GOV_RESOURCE_ID", res)
        if urlopen is not None:
            monkeypatch.setattr(ml.urllib.request, "urlopen", urlopen)
        return ml.diagnose(commodity="Tomato")

    def test_missing_key_is_reported_as_such(self, monkeypatch):
        out = self._diagnose(monkeypatch, None, key="", res="")
        assert out["status"] == "key_missing"
        assert "DATA_GOV_API_KEY" in out["message"]

    def test_todays_row_reports_live(self, monkeypatch):
        import datetime
        today = datetime.date.today()
        out = self._diagnose(monkeypatch, self._stub([self._row(today)]))
        assert out["status"] == "live"
        assert out["records_dated_today"] == 1

    def test_only_older_rows_is_not_live_and_says_why(self, monkeypatch):
        import datetime
        old = datetime.date.today() - datetime.timedelta(days=3)
        out = self._diagnose(monkeypatch, self._stub([self._row(old)]))
        assert out["status"] == "no_current_record"
        assert out["records_dated_today"] == 0
        assert out["newest_date_returned"] == old.isoformat()
        assert "no current record" in out["message"].lower()

    def test_zero_rows_is_distinct_from_no_current_record(self, monkeypatch):
        out = self._diagnose(monkeypatch, self._stub([]))
        assert out["status"] == "no_records"

    def test_a_rejected_key_is_reported_as_auth_failure(self, monkeypatch):
        import services.mandi_live as ml

        def _401(*a, **k):
            raise ml.urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

        out = self._diagnose(monkeypatch, _401)
        assert out["status"] == "auth_failed"
        assert "authentication failed" in out["message"].lower()

    def test_network_failure_is_not_confused_with_a_bad_key(self, monkeypatch):
        out = self._diagnose(monkeypatch,
                             lambda *a, **k: (_ for _ in ()).throw(OSError("no route")))
        assert out["status"] == "unreachable"

    def test_an_unexpected_payload_is_flagged(self, monkeypatch):
        class _Bad:
            status = 200
            def read(_s): return b'{"message":"something else"}'
            def __enter__(_s): return _s
            def __exit__(_s, *a): return False
        out = self._diagnose(monkeypatch, lambda *a, **k: _Bad())
        assert out["status"] == "bad_payload"

    def test_the_api_key_is_never_echoed_back(self, monkeypatch):
        import datetime
        out = self._diagnose(monkeypatch,
                             self._stub([self._row(datetime.date.today())]),
                             key="SUPERSECRET123")
        assert "SUPERSECRET123" not in json.dumps(out)
        assert "REDACTED" in out["request_url"]

    def test_endpoint_is_reachable_and_shaped(self, client):
        body = client.get("/api/market-prices/diagnostics?commodity=Tomato").get_json()
        for key in ("status", "message", "api_key_present", "today"):
            assert key in body

    def test_live_feed_carries_the_status_contract(self, monkeypatch):
        """The frontend must key off status/is_live, never off key presence."""
        import datetime
        import services.mandi_live as ml
        monkeypatch.setattr(config, "DATA_GOV_API_KEY", "k")
        monkeypatch.setattr(config, "DATA_GOV_RESOURCE_ID", "r")
        monkeypatch.setattr(ml, "_CACHE", {})
        monkeypatch.setattr(ml.urllib.request, "urlopen",
                            self._stub([self._row(datetime.date.today())]))
        out = ml.fetch_live_prices(commodity="Tomato")
        assert out["status"] == "live" and out["is_live"] is True
        assert out["data_date"] == datetime.date.today().isoformat()

        monkeypatch.setattr(ml, "_CACHE", {})
        old = datetime.date.today() - datetime.timedelta(days=2)
        monkeypatch.setattr(ml.urllib.request, "urlopen", self._stub([self._row(old)]))
        out2 = ml.fetch_live_prices(commodity="Tomato")
        assert out2["status"] == "fallback" and out2["is_live"] is False

    def test_ui_no_longer_claims_the_api_is_configured_as_if_working(self):
        import os
        path = os.path.join(os.path.dirname(__file__), "..",
                            "frontend", "js", "step4-farmer.js")
        if not os.path.exists(path):
            pytest.skip("step4-farmer.js not present")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "'Official API configured.'" not in src

    def test_the_market_price_ui_only_labels_live_when_the_feed_says_so(self):
        import os
        path = os.path.join(os.path.dirname(__file__), "..",
                            "frontend", "pages", "farmer.html")
        if not os.path.exists(path):
            pytest.skip("farmer.html not present")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        # the LIVE branch must be gated on the feed's own flag
        assert "live.live" in src, "LIVE is no longer gated on the feed's flag"
        assert "result.is_live" in src


# ---------------------------------------------------------------------------
# 32. memory-safe archive loading
# ---------------------------------------------------------------------------

class TestMemorySafeArchiveLoad:
    """
    Startup died with "Error tokenizing data. C error: out of memory" on a full
    archive. Causes: read_csv(low_memory=False) pulling every column and the
    whole file in at once; six text columns held as Python string objects; four
    more full-width lowercase copies added on top; and one pd.concat holding
    every input plus the copy at the same time.
    """

    def test_csv_reader_declares_columns_and_dtypes(self):
        """low_memory=False is what forced whole-file dtype inference."""
        import ast
        import inspect
        from ml import data_loader as dl

        src = inspect.getsource(dl._load_arrival)
        # Strip the docstring, which legitimately names the old bug.
        tree = ast.parse(src.lstrip())
        fn = tree.body[0]
        if (fn.body and isinstance(fn.body[0], ast.Expr)
                and isinstance(fn.body[0].value, ast.Constant)):
            fn.body = fn.body[1:]
        code = ast.unparse(fn)
        assert "low_memory=False" not in code, "the memory-hungry read is back"
        for needed in ("usecols", "chunksize", "dtype"):
            assert needed in code, f"_load_arrival no longer uses {needed}"

    def test_only_the_needed_columns_are_read(self):
        from ml import data_loader as dl, config as cfg
        assert cfg.COL_MODAL_PRICE in dl._WANTED_COLUMNS
        assert "Commodity_Code" not in dl._WANTED_COLUMNS

    def test_shrink_categorises_text_whatever_dtype_pandas_used(self):
        """
        Only checking for "object" silently skipped five of the six text
        columns — the ones that actually dominate memory.
        """
        from ml import data_loader as dl, config as cfg
        for dtype in ("object", "string"):
            df = pd.DataFrame({
                cfg.COL_STATE: pd.Series(["Punjab"] * 100, dtype=dtype),
                cfg.COL_MARKET: pd.Series(["Ahmedgarh"] * 100, dtype=dtype),
                cfg.COL_MODAL_PRICE: pd.Series([1700.0] * 100, dtype="float64"),
            })
            out = dl._shrink(df)
            assert str(out[cfg.COL_STATE].dtype) == "category", dtype
            assert str(out[cfg.COL_MARKET].dtype) == "category", dtype
            assert str(out[cfg.COL_MODAL_PRICE].dtype) == "float32"

    def test_categorising_actually_saves_memory_and_keeps_values(self):
        from ml import data_loader as dl, config as cfg
        n = 50000
        df = pd.DataFrame({
            cfg.COL_STATE: ["Maharashtra"] * n,
            cfg.COL_DISTRICT: ["Nashik"] * n,
            cfg.COL_MARKET: ["Pimpalgaon"] * n,
            cfg.COL_COMMODITY: ["Onion"] * n,
            cfg.COL_MODAL_PRICE: [1700.0] * n,
        })
        before = df.memory_usage(deep=True).sum()
        out = dl._shrink(df.copy())
        after = out.memory_usage(deep=True).sum()
        assert after < before / 4, f"no real saving: {before} -> {after}"
        assert list(out[cfg.COL_MARKET].astype(str).unique()) == ["Pimpalgaon"]

    def test_filter_columns_are_categorical_and_still_match(self):
        """These four lowercase copies were plain strings — hundreds of MB."""
        from ml import data_loader as dl, config as cfg
        df = pd.DataFrame({
            cfg.COL_COMMODITY: pd.Categorical(["Onion", "ONION", "Tomato"]),
            cfg.COL_STATE: pd.Categorical(["Maharashtra"] * 3),
            cfg.COL_DISTRICT: pd.Categorical(["Nashik"] * 3),
            cfg.COL_MARKET: pd.Categorical(["Pimpalgaon"] * 3),
        })
        out = dl._add_filter_columns(df)
        assert str(out["_commodity_l"].dtype) == "category"
        # spellings that differ only in case must collapse to one lookup value
        assert (out["_commodity_l"] == "onion").sum() == 2
        assert (out["_commodity_l"] == "tomato").sum() == 1

    def test_cache_write_is_atomic(self):
        """A crash mid-write must not leave a half pickle that looks valid."""
        import inspect
        from ml import data_loader as dl
        src = inspect.getsource(dl._write_cache)
        assert "os.replace" in src, "cache write is not atomic"
        assert ".tmp" in src

    def test_concat_releases_each_source(self):
        import inspect
        from ml import data_loader as dl
        src = inspect.getsource(dl.load_combined_data)
        assert "pd.concat(frames, ignore_index=True)" not in src, \
            "the all-at-once concat is back"
        assert "frames[i] = None" in src

    def test_market_groupbys_pass_observed_true(self):
        """
        With a categorical market column the default iterates every market in
        the archive, not the ones present in the slice.
        """
        import os, re
        path = os.path.join(os.path.dirname(__file__), "..", "backend", "app.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for m in re.finditer(r"groupby\(ml_config\.COL_MARKET([^)]*)\)", src):
            assert "observed=True" in m.group(1), \
                "a market groupby would iterate unused categories"


# ---------------------------------------------------------------------------
# 33. an archive that fails to load must say so, not look empty
# ---------------------------------------------------------------------------

class TestArchiveFailureIsHonest:
    def _app_with_error(self, message="out of memory"):
        import backend.app as appmod
        application = appmod.create_app(load_real_data=False, load_chronos=False)
        application.config["TESTING"] = True
        store = application.extensions["kisanlink"]
        store["data_pending"] = False
        store["data_error"] = message
        return application

    def test_failed_archive_returns_503_with_a_reason(self):
        app_ = self._app_with_error()
        res = app_.test_client().get("/api/commodities")
        assert res.status_code == 503
        body = res.get_json()
        assert body["reason"] == "archive_load_failed"
        assert body["success"] is False

    def test_failure_is_distinct_from_still_loading(self):
        import backend.app as appmod
        application = appmod.create_app(load_real_data=False, load_chronos=False)
        application.config["TESTING"] = True
        application.extensions["kisanlink"]["data_pending"] = True
        body = application.test_client().get("/api/commodities").get_json()
        assert body["reason"] == "data_warming_up"

    def test_data_status_reports_the_failure(self):
        app_ = self._app_with_error("the archive did not fit in memory")
        body = app_.test_client().get("/api/data-status").get_json()
        assert body["ready"] is False
        assert body["failed"] is True
        assert "memory" in (body["error"] or "")

    def test_features_that_do_not_need_the_archive_still_work(self):
        """A dead archive must not take quality, weather or auth down."""
        app_ = self._app_with_error()
        c = app_.test_client()
        assert c.get("/api/ml/quality-status").status_code == 200
        assert c.get("/api/data-status").status_code == 200
        res = c.post("/api/assistant/message", json={"message": "help", "lang": "en"})
        assert res.status_code == 200
