"""The weighted matching engine."""
import pytest

from ml.matching_model import score_distance, score_match, score_price, score_quality, score_quantity

WEIGHTS = {"price": 0.35, "quantity": 0.20, "quality": 0.20, "distance": 0.15, "trust": 0.10}


def test_price_at_the_benchmark_scores_the_midpoint():
    assert score_price(2500, 2500)["score"] == pytest.approx(0.5)


def test_price_above_the_benchmark_scores_higher():
    better = score_price(3000, 2500)["score"]
    worse = score_price(2000, 2500)["score"]
    assert better > 0.5 > worse


def test_price_without_a_benchmark_is_neutral_and_says_so():
    result = score_price(2500, None)
    assert result["score"] == 0.5
    assert result["available"] is False
    assert "No recent market price" in result["reason"]


def test_quantity_fit_penalises_a_buyer_who_takes_a_sliver_of_the_lot():
    full = score_quantity(100, 100)["score"]
    sliver = score_quantity(100, 5)["score"]
    assert full == pytest.approx(1.0)
    assert sliver < 0.6


def test_grade_below_requirement_is_treated_as_blocking():
    result = score_quality("C", "A")
    assert result["score"] == 0.0
    assert result["blocking"] is True


def test_grade_above_requirement_passes_cleanly():
    assert score_quality("A", "C")["score"] == pytest.approx(1.0)


def test_excess_moisture_halves_the_quality_score():
    within = score_quality("A", "A", lot_moisture=8, max_moisture=12)["score"]
    over = score_quality("A", "A", lot_moisture=18, max_moisture=12)["score"]
    assert over == pytest.approx(within * 0.5)


def test_missing_coordinates_fall_back_to_district_proximity():
    result = score_distance(None, 300, proximity="SAME_DISTRICT")
    assert result["available"] is False
    assert result["score"] > score_distance(None, 300, proximity="OTHER")["score"]
    assert "coordinates missing" in result["reason"]


def test_a_blocked_match_is_reported_but_not_silently_dropped():
    result = score_match(
        {"quantity": 100, "grade": "C"},
        {"price": 2500, "required_quantity": 100, "min_grade": "A"},
        WEIGHTS,
        benchmark_price=2500,
    )
    assert result["is_viable"] is False
    assert result["blockers"]
    assert result["total_score"] > 0  # still comparable, just flagged


def test_component_weights_sum_into_the_total():
    result = score_match(
        {"quantity": 100, "grade": "A"},
        {
            "price": 2700,
            "required_quantity": 100,
            "min_grade": "B",
            "distance_km": 30,
            "verification_status": "PLATFORM_REVIEWED",
            "trust_score": 80,
        },
        WEIGHTS,
        benchmark_price=2500,
    )
    total = sum(part["weighted_score"] for part in result["components"].values())
    assert result["total_score"] == pytest.approx(round(total * 100, 2), abs=0.05)


def test_lot_matching_returns_ranked_explained_options(api, listed_tomato_lot):
    data = api.data("get", f"/api/lots/{listed_tomato_lot['id']}/matches", "farmer")
    assert data["matches"], "the demo scenario should produce buyer matches"
    ranks = [match["rank"] for match in data["matches"]]
    assert ranks == sorted(ranks)
    top = data["matches"][0]
    assert set(top["score_components"]) == {"price", "quantity", "quality", "distance", "trust"}
    assert all(component["reason"] for component in top["score_components"].values())


def test_weights_are_declared_in_the_response(api, listed_tomato_lot):
    """The farmer is entitled to see what the ranking was weighted on."""
    data = api.data("get", f"/api/lots/{listed_tomato_lot['id']}/matches", "farmer")
    assert data["weights"]["price"] == pytest.approx(0.35)
    assert "not learned from data" in data["weights_note"]


def test_buyer_side_matching_supports_aggregation(api):
    demands = api.data("get", "/api/buyer-demands?mine=true", "processor")
    demand_id = demands[0]["id"]
    data = api.data("get", f"/api/buyer-demands/{demand_id}/matches", "processor")
    assert "aggregation" in data
    assert data["aggregation"]["remaining_quantity"] >= 0
