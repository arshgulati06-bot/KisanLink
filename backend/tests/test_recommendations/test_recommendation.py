"""The explainable recommendation and the sale-window advice."""
import pytest

from ml.forecast_model import forecast_prices
from ml.recommendation_engine import (
    CONSIDER_WAITING,
    INSUFFICIENT_DATA,
    SELL_NOW,
    net_adjusted_weights,
    net_realization,
    sale_window_advice,
)

WEIGHTS = {"price": 0.35, "quantity": 0.20, "quality": 0.20, "distance": 0.15, "trust": 0.10}


# --- net realization -------------------------------------------------------
def test_net_realization_itemises_every_deduction():
    result = net_realization(100000, {"transport": 4000, "commission": 3000})
    assert result["net_amount"] == 93000
    assert result["total_deductions"] == 7000
    assert result["deductions"]["storage"] == 0
    assert result["deduction_percent"] == 7.0


def test_weights_are_rebalanced_when_ranking_on_net_price():
    """Transport is already inside the net price, so distance must not double-count."""
    adjusted = net_adjusted_weights(WEIGHTS)
    assert adjusted["distance"] == pytest.approx(0.075)
    assert adjusted["price"] == pytest.approx(0.425)
    assert sum(adjusted.values()) == pytest.approx(sum(WEIGHTS.values()))


# --- forecasting -----------------------------------------------------------
def _series(count, start=2000, step=10):
    return [
        {"price_date": f"2026-01-{day + 1:02d}", "modal_price": start + step * day}
        for day in range(count)
    ]


def test_forecast_refuses_to_guess_from_thin_history():
    result = forecast_prices(_series(5), horizon_days=7, min_points=10)
    assert result["available"] is False
    assert result["method"] == "INSUFFICIENT_DATA"
    assert "Insufficient historical data" in result["reason"]
    assert "forecast_price" not in result


def test_forecast_projects_a_clean_upward_trend():
    result = forecast_prices(_series(30), horizon_days=7, min_points=10)
    assert result["available"] is True
    assert result["trend"] == "RISING"
    assert result["forecast_price"] > result["latest_price"]
    assert result["lower_bound"] <= result["forecast_price"] <= result["upper_bound"]


def test_a_weak_fit_falls_back_and_flags_the_trend_as_unreliable():
    noisy = [
        {"price_date": f"2026-01-{day + 1:02d}", "modal_price": 2000 + (400 if day % 2 else -400)}
        for day in range(30)
    ]
    result = forecast_prices(noisy, horizon_days=7, min_points=10)
    assert result["method"] == "MOVING_AVERAGE"
    assert result["trend_is_reliable"] is False


# --- sale window -----------------------------------------------------------
def test_no_forecast_means_no_timing_advice():
    advice = sale_window_advice(
        {"available": False, "reason": "Insufficient historical data."},
        best_net_price_per_unit=2500,
        holding_cost_per_unit=20,
        horizon_days=7,
    )
    assert advice["recommendation"] == INSUFFICIENT_DATA
    assert any("reliable timing" in reason for reason in advice["reasons"])


def test_a_perishable_crop_is_never_told_to_wait():
    advice = sale_window_advice(
        {"available": True, "trend": "RISING", "confidence": "HIGH",
         "expected_change_percent": 25, "history_days": 60, "trend_is_reliable": True},
        best_net_price_per_unit=2500,
        holding_cost_per_unit=5,
        horizon_days=14,
        is_perishable=True,
        shelf_life_days=10,
    )
    assert advice["recommendation"] == SELL_NOW


def test_waiting_is_advised_only_when_the_gain_beats_holding_cost():
    forecast = {
        "available": True, "trend": "RISING", "confidence": "HIGH",
        "expected_change_percent": 8.0, "history_days": 60, "trend_is_reliable": True,
    }
    worth_it = sale_window_advice(forecast, 2500, holding_cost_per_unit=20, horizon_days=7)
    not_worth_it = sale_window_advice(forecast, 2500, holding_cost_per_unit=400, horizon_days=7)
    assert worth_it["recommendation"] == CONSIDER_WAITING
    assert not_worth_it["recommendation"] == SELL_NOW


def test_an_unreliable_trend_never_justifies_holding():
    advice = sale_window_advice(
        {"available": True, "trend": "RISING", "confidence": "HIGH",
         "expected_change_percent": 30, "history_days": 60, "trend_is_reliable": False},
        best_net_price_per_unit=2500,
        holding_cost_per_unit=20,
        horizon_days=7,
    )
    assert advice["recommendation"] != CONSIDER_WAITING
    assert any("dependable price trend" in reason for reason in advice["reasons"])


# --- the full endpoint -----------------------------------------------------
def test_recommendation_compares_mandis_and_buyers_together(api, listed_tomato_lot):
    data = api.data("get", f"/api/lots/{listed_tomato_lot['id']}/recommendation", "farmer")
    channels = {row["option_type"] for row in data["comparison"]}
    assert "MARKET" in channels and "BUYER" in channels
    assert len(data["comparison"]) >= 4


def test_every_option_is_costed_down_to_a_net_price(api, listed_tomato_lot):
    data = api.data("get", f"/api/lots/{listed_tomato_lot['id']}/recommendation", "farmer")
    for row in data["comparison"]:
        assert row["gross_price_per_unit"] is not None
        assert row["net_price_per_unit"] is not None
        # Net can never exceed gross: something is always deducted or nothing is.
        assert row["net_price_per_unit"] <= row["gross_price_per_unit"] + 0.01


def test_mandi_options_deduct_commission_and_market_fee(api, listed_tomato_lot):
    data = api.data("get", f"/api/lots/{listed_tomato_lot['id']}/recommendation", "farmer")
    mandi = next(o for o in data["options"] if o["option_type"] == "MARKET")
    assert mandi["realization"]["deductions"]["commission"] > 0
    assert "commission" in mandi["cost_note"]


def test_farm_gate_buyers_carry_no_transport_cost_for_the_farmer(api, listed_tomato_lot):
    data = api.data("get", f"/api/lots/{listed_tomato_lot['id']}/recommendation", "farmer")
    farm_gate = [o for o in data["options"] if o.get("delivery_mode") == "FARM_GATE"]
    assert farm_gate, "the demo scenario includes a farm-gate buyer"
    assert farm_gate[0]["realization"]["deductions"]["transport"] == 0
    assert farm_gate[0]["transport_borne_by"] == "BUYER"


def test_recommendation_explains_itself(api, listed_tomato_lot):
    data = api.data("get", f"/api/lots/{listed_tomato_lot['id']}/recommendation", "farmer")
    reasons = data["why_this_recommendation"]
    assert len(reasons) >= 4
    assert any("market price" in reason for reason in reasons)
    assert any("km" in reason for reason in reasons)


def test_recommendation_states_that_costs_are_estimates(api, listed_tomato_lot):
    data = api.data("get", f"/api/lots/{listed_tomato_lot['id']}/recommendation", "farmer")
    assert "estimates" in data["disclaimer"]
    assert "platform review" in data["disclaimer"]


def test_unit_conversion_holds_between_a_kg_lot_and_quintal_demand(api, listed_tomato_lot):
    """The demo lot is in kilograms while buyers quote per quintal."""
    assert listed_tomato_lot["unit"] == "KG"
    data = api.data("get", f"/api/lots/{listed_tomato_lot['id']}/recommendation", "farmer")
    buyer_option = next(o for o in data["options"] if o["option_type"] == "BUYER")
    assert buyer_option["unit"] == "KG"
    # A per-quintal price in the thousands must land in the tens per kilogram.
    assert 5 < buyer_option["gross_price_per_unit"] < 200


def test_recommendation_is_stored_so_advice_can_be_reproduced(api, listed_tomato_lot):
    lot_id = listed_tomato_lot["id"]
    api.data("post", "/api/recommendations", "farmer", json={"lot_id": lot_id, "store": True})
    stored = api.data("get", f"/api/recommendations/lot/{lot_id}/latest", "farmer")
    assert stored["recommended_label"]
    assert stored["payload"]["comparison"]
    assert stored["sale_window"] in (
        "SELL_NOW", "CONSIDER_WAITING", "MONITOR", "INSUFFICIENT_DATA"
    )


def test_sale_window_endpoint_returns_advice_and_its_basis(api, listed_tomato_lot):
    data = api.data(
        "post", "/api/recommendations/sale-window", "farmer",
        json={"lot_id": listed_tomato_lot["id"], "horizon_days": 7},
    )
    assert data["sale_window"]["recommendation"]
    assert data["sale_window"]["reasons"]
    assert "storage" in data
