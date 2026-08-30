"""Transport estimation and transport requests."""
import pytest

from app.services.logistics_service import choose_vehicle, estimate_transport
from app.services.maps_service import haversine_km, road_distance_km


def test_haversine_matches_a_known_distance():
    """Pune to Nashik is roughly 165 km straight line."""
    distance = haversine_km(18.5204, 73.8567, 19.9975, 73.7898)
    assert 160 < distance < 175


def test_road_distance_is_scaled_above_the_straight_line():
    straight = haversine_km(18.5204, 73.8567, 19.9975, 73.7898)
    road = road_distance_km(18.5204, 73.8567, 19.9975, 73.7898)
    assert road > straight


def test_cost_rises_with_distance_and_with_load():
    near = estimate_transport(100, "QUINTAL", 20)["estimated_cost"]
    far = estimate_transport(100, "QUINTAL", 200)["estimated_cost"]
    heavy = estimate_transport(400, "QUINTAL", 200)["estimated_cost"]
    assert near < far < heavy


def test_a_minimum_charge_applies_to_tiny_movements():
    result = estimate_transport(1, "QUINTAL", 2)
    assert result["breakdown"]["minimum_charge_applied"] is True


def test_vehicle_is_chosen_by_load():
    assert choose_vehicle(1.0)[0] == "TEMPO"
    assert choose_vehicle(8.0)[0] == "TRUCK_9T"
    assert choose_vehicle(40.0)[0] == "TRUCK_16T"


def test_estimates_are_labelled_as_estimates(api):
    data = api.data("post", "/api/logistics/estimate",
                    json={"quantity": 100, "unit": "QUINTAL", "distance_km": 120})
    assert data["is_estimate"] is True
    assert "not a transporter's quotation" in data["assumptions"]


def test_unknown_distance_gives_no_cost_rather_than_a_guess(api):
    data = api.data(
        "post", "/api/logistics/estimate",
        json={"quantity": 100, "unit": "QUINTAL",
              "from_district": "Nashik", "to_district": "Pune"},
    )
    assert data["available"] is False
    assert data["estimated_cost"] is None


def test_estimate_between_two_points_measures_the_distance(api):
    data = api.data(
        "post", "/api/logistics/estimate",
        json={
            "quantity": 100, "unit": "QUINTAL",
            "from_latitude": 20.05, "from_longitude": 73.85,
            "to_latitude": 18.76, "to_longitude": 74.23,
        },
    )
    assert data["available"] is True
    assert data["distance_km"] > 100
    assert data["distance"]["method"] == "MEASURED_STRAIGHT_LINE"


@pytest.fixture()
def transport_request(api):
    crops = api.data("get", "/api/crops?q=Potato")
    lot = api.data("post", "/api/lots", "farmer",
                   json={"crop_id": crops[0]["id"], "quantity": 25, "unit": "QUINTAL",
                         "district": "Nashik", "latitude": 20.05, "longitude": 73.85},
                   expect=201)
    return api.data(
        "post", "/api/logistics/requests", "farmer",
        json={"lot_id": lot["id"], "drop_district": "Pune",
              "drop_latitude": 18.76, "drop_longitude": 74.23},
        expect=201,
    )


def test_request_is_costed_and_a_vehicle_suggested(transport_request):
    assert transport_request["status"] == "REQUESTED"
    assert transport_request["distance_km"] > 0
    assert transport_request["estimated_cost"] > 0
    assert transport_request["vehicle_type"]


def test_status_follows_the_defined_flow(api, transport_request):
    request_id = transport_request["id"]
    status, body = api.put(f"/api/logistics/requests/{request_id}/status", "farmer",
                           json={"status": "DELIVERED"})
    assert status == 422
    assert "cannot move to" in body["error"]["message"]

    for step in ("ASSIGNED", "IN_TRANSIT", "DELIVERED"):
        api.data("put", f"/api/logistics/requests/{request_id}/status", "farmer",
                 json={"status": step})


def test_assigning_a_provider_advances_the_request(api, transport_request):
    data = api.data(
        "put", f"/api/logistics/requests/{transport_request['id']}/provider", "farmer",
        json={"provider_name": "Demo Transport", "provider_phone": "9876543210"},
    )
    assert data["status"] == "ASSIGNED"
    assert data["provider_name"] == "Demo Transport"


def test_others_cannot_move_someone_elses_request(api, transport_request):
    status, _ = api.put(f"/api/logistics/requests/{transport_request['id']}/status",
                        "farmer3", json={"status": "ASSIGNED"})
    assert status == 403
