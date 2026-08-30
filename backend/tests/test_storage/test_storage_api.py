"""Storage directory and holding-cost estimation."""
from app.services.storage_service import estimate_storage_cost


def test_facility_directory_is_public(api):
    data = api.data("get", "/api/storage/facilities")
    assert data
    assert all("cost_per_tonne_per_day" in facility for facility in data)


def test_demo_facilities_are_flagged_as_seed_data(api):
    data = api.data("get", "/api/storage/facilities")
    assert all(facility["is_seed_data"] is True for facility in data)


def test_cold_storage_can_be_filtered(api):
    data = api.data("get", "/api/storage/facilities?cold_only=true")
    assert data
    assert all(facility["has_cold_storage"] is True for facility in data)


def test_nearby_prefers_the_farmers_own_district_without_coordinates(api):
    data = api.data("get", "/api/storage/nearby?district=Nashik&required_tonnes=1")
    assert data[0]["proximity"] == "SAME_DISTRICT"


def test_nearby_is_ordered_by_distance_with_coordinates(api):
    data = api.data("get", "/api/storage/nearby?latitude=20.05&longitude=73.85")
    distances = [f["distance_km"] for f in data if f["distance_km"] is not None]
    assert distances == sorted(distances)


def test_nearby_requires_a_location(api):
    status, _ = api.get("/api/storage/nearby")
    assert status == 422


def test_capacity_filter_excludes_facilities_that_are_too_small(api):
    data = api.data("get", "/api/storage/nearby?district=Nashik&required_tonnes=100000")
    assert data == []


def test_holding_cost_grows_with_time():
    week = estimate_storage_cost(100, "QUINTAL", 7)["storage_charge"]
    month = estimate_storage_cost(100, "QUINTAL", 30)["storage_charge"]
    assert month > week > 0


def test_perishables_carry_a_higher_loss_allowance():
    """Otherwise the model would happily suggest holding a crop that rots."""
    stable = estimate_storage_cost(100, "QUINTAL", 10)["expected_loss_percent"]
    perishable = estimate_storage_cost(100, "QUINTAL", 10, crop_is_perishable=True)
    assert perishable["expected_loss_percent"] == stable * 2


def test_estimate_endpoint_prices_both_charge_and_loss(api):
    data = api.data(
        "post", "/api/storage/estimate",
        json={"quantity": 100, "unit": "QUINTAL", "days": 14, "price_per_unit": 2700},
    )
    assert data["charge_per_unit"] > 0
    assert data["loss_value_per_unit"] > 0
    assert data["holding_cost_per_unit"] == round(
        data["charge_per_unit"] + data["loss_value_per_unit"], 2
    )


def test_only_admins_add_facilities(api):
    payload = {"name": "Unauthorised Store", "district": "Pune"}
    status, _ = api.post("/api/storage/facilities", "farmer", json=payload)
    assert status == 403
    api.data("post", "/api/storage/facilities", "admin",
             json={"name": "Test Warehouse", "district": "Pune",
                   "capacity_tonnes": 100, "cost_per_tonne_per_day": 9},
             expect=201)
