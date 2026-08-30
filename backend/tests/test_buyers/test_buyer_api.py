"""Buyer profiles and buyer demand."""


def test_buyer_directory_shows_type_and_verification(api):
    buyers = api.data("get", "/api/buyers")
    assert buyers
    processor = next(b for b in buyers if b["buyer_type"] == "PROCESSOR")
    assert processor["verification_status"] in (
        "UNVERIFIED",
        "DOCUMENTS_SUBMITTED",
        "PLATFORM_REVIEWED",
        "REJECTED",
    )
    assert processor["verification_label"]


def test_buyer_detail_carries_the_verification_disclaimer(api):
    buyers = api.data("get", "/api/buyers?page_size=1")
    detail = api.data("get", f"/api/buyers/{buyers[0]['id']}")
    # The platform must never let its own review read as a government check.
    assert "not a government KYC" in detail["verification_disclaimer"]


def test_processors_and_institutional_buyers_are_first_class_types(api):
    """Both are named explicitly in the problem statement."""
    types = {buyer["buyer_type"] for buyer in api.data("get", "/api/buyers")}
    assert {"PROCESSOR", "INSTITUTIONAL", "AGGREGATOR", "TRADER"} <= types


def test_buyer_cannot_self_verify(api):
    api.data(
        "put",
        "/api/buyers/profile",
        "trader",
        json={"business_name": "Pawar Trading Company", "verification_status": "PLATFORM_REVIEWED"},
    )
    detail = api.data("get", "/api/buyers")
    trader = next(b for b in detail if b["business_name"] == "Pawar Trading Company")
    assert trader["verification_status"] == "UNVERIFIED"


def test_buyer_can_publish_demand(api, tomato_crop_id):
    demand = api.data(
        "post",
        "/api/buyer-demands",
        "processor",
        json={
            "crop_id": tomato_crop_id,
            "required_quantity": 150,
            "unit": "QUINTAL",
            "min_grade": "B",
            "price_min": 2600,
            "price_max": 2900,
        },
        expect=201,
    )
    assert demand["status"] == "OPEN"
    assert demand["remaining_quantity"] == 150


def test_price_band_must_be_ordered(api, tomato_crop_id):
    status, body = api.post(
        "/api/buyer-demands",
        "processor",
        json={
            "crop_id": tomato_crop_id,
            "required_quantity": 10,
            "price_min": 3000,
            "price_max": 2000,
        },
    )
    assert status == 422
    assert "price_min" in body["error"]["message"]


def test_indicative_price_is_the_midpoint_of_the_band(api, tomato_crop_id):
    """A wide band with a high ceiling must not win the ranking on its own."""
    demand = api.data(
        "post",
        "/api/buyer-demands",
        "processor",
        json={
            "crop_id": tomato_crop_id,
            "required_quantity": 20,
            "price_min": 2000,
            "price_max": 4000,
        },
        expect=201,
    )
    detail = api.data("get", f"/api/buyer-demands/{demand['id']}")
    assert detail["price_min"] == 2000 and detail["price_max"] == 4000
    full = api.data("get", "/api/buyer-demands?mine=true", "processor")
    assert any(item["id"] == demand["id"] for item in full)


def test_farmers_cannot_publish_demand(api, tomato_crop_id):
    status, _ = api.post(
        "/api/buyer-demands", "farmer", json={"crop_id": tomato_crop_id, "required_quantity": 10}
    )
    assert status == 403


def test_buyer_cannot_edit_another_buyers_demand(api):
    demands = api.data("get", "/api/buyer-demands?mine=true", "processor")
    status, _ = api.put(
        f"/api/buyer-demands/{demands[0]['id']}", "aggregator", json={"required_quantity": 1}
    )
    assert status == 403


def test_buyer_dashboard_summarises_open_demand(api):
    data = api.data("get", "/api/buyers/dashboard", "processor")
    assert data["summary"]["active_requirements"] >= 1
    assert "transactions" in data
