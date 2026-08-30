"""Market prices, trends, arrivals and nearby-market comparison."""


def test_latest_prices_report_several_markets(api, tomato_crop_id):
    data = api.data("get", f"/api/prices?crop_id={tomato_crop_id}")
    assert data["markets_reporting"] >= 3
    assert all("modal_price" in row for row in data["prices"])


def test_demo_prices_are_labelled_as_demo_data(api, tomato_crop_id):
    """The project must never let seeded prices pass as official data."""
    data = api.data("get", f"/api/prices?crop_id={tomato_crop_id}")
    assert "demonstration" in data["data_note"].lower()
    assert all(row["is_official_source"] is False for row in data["prices"])


def test_overview_exposes_the_price_spread(api, tomato_crop_id):
    data = api.data("get", f"/api/prices/overview?crop_id={tomato_crop_id}")
    assert data["highest_price"] > data["lowest_price"]
    assert data["price_spread"] == round(data["highest_price"] - data["lowest_price"], 2)
    assert "spread_note" in data


def test_trend_series_includes_a_smoothing_line(api, tomato_crop_id):
    data = api.data("get", f"/api/prices/trends?crop_id={tomato_crop_id}&days=30")
    assert data["data_points"] > 10
    assert all("moving_average_7d" in point for point in data["series"])


def test_nearby_markets_are_ordered_by_distance(api, tomato_crop_id):
    data = api.data(
        "get",
        f"/api/markets/nearby?latitude=20.05&longitude=73.85&crop_id={tomato_crop_id}&limit=5",
    )
    distances = [market["distance_km"] for market in data if market["distance_km"] is not None]
    assert distances == sorted(distances)
    assert data[0]["name"] == "Nashik Panchavati"


def test_nearby_requires_a_location(api):
    status, body = api.get("/api/markets/nearby")
    assert status == 422
    assert "district" in body["error"]["message"]


def test_arrivals_are_reported_when_published(api, tomato_crop_id):
    markets = api.data("get", "/api/markets?q=Nashik Panchavati")
    market_id = markets[0]["id"]
    data = api.data("get", f"/api/markets/{market_id}/arrivals?crop_id={tomato_crop_id}&days=20")
    assert data["summary"]["available"] is True
    assert data["summary"]["direction"] in ("RISING", "FALLING", "STABLE")


def test_missing_arrivals_are_reported_as_unavailable(api, tomato_crop_id):
    """Vashi publishes no arrivals in the demo data; that must be said, not faked."""
    markets = api.data("get", "/api/markets?q=Vashi")
    market_id = markets[0]["id"]
    data = api.data("get", f"/api/markets/{market_id}/arrivals?crop_id={tomato_crop_id}")
    assert data["summary"]["available"] is False
    assert all(row["arrival_quantity"] is None for row in data["series"])


def test_benchmark_price_converts_units(api, tomato_crop_id):
    per_quintal = api.data("get", f"/api/prices/benchmark?crop_id={tomato_crop_id}&unit=QUINTAL")
    per_kg = api.data("get", f"/api/prices/benchmark?crop_id={tomato_crop_id}&unit=KG")
    assert per_quintal["available"] is True
    assert round(per_kg["price"] * 100, 0) == round(per_quintal["price"], 0)


def test_only_admins_can_record_prices(api, tomato_crop_id):
    markets = api.data("get", "/api/markets?page_size=1")
    payload = {
        "market_id": markets[0]["id"],
        "crop_id": tomato_crop_id,
        "price_date": "2026-01-15",
        "modal_price": 2500,
    }
    status, _ = api.post("/api/prices", "farmer", json=payload)
    assert status == 403
    api.data("post", "/api/prices", "admin", json=payload, expect=201)


def test_reloading_the_same_day_updates_instead_of_duplicating(api, tomato_crop_id):
    markets = api.data("get", "/api/markets?page_size=1")
    payload = {
        "market_id": markets[0]["id"],
        "crop_id": tomato_crop_id,
        "price_date": "2026-01-16",
        "modal_price": 2500,
    }
    api.data("post", "/api/prices", "admin", json=payload, expect=201)
    payload["modal_price"] = 2650
    updated = api.data("post", "/api/prices", "admin", json=payload, expect=200)
    assert updated["modal_price"] == 2650
