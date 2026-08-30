"""Crop master data."""


def test_crop_list_is_public_and_paginated(api):
    status, body = api.get("/api/crops?page_size=5")
    assert status == 200
    assert len(body["data"]) == 5
    assert body["meta"]["total"] >= 16
    assert body["meta"]["has_next"] is True


def test_crop_carries_perishability_and_grades(api, tomato_crop_id):
    crop = api.data("get", f"/api/crops/{tomato_crop_id}")
    assert crop["name"] == "Tomato"
    # Perishability drives the sale-window advice, so it must be a real boolean.
    assert crop["is_perishable"] is True
    assert crop["shelf_life_days"] == 10


def test_unknown_crop_returns_404(api):
    status, body = api.get("/api/crops/999999")
    assert status == 404
    assert body["error"]["code"] == "NOT_FOUND"


def test_only_admins_can_add_a_crop(api):
    status, _ = api.post("/api/crops", "farmer", json={"name": "Millet"})
    assert status == 403
    data = api.data(
        "post",
        "/api/crops",
        "admin",
        json={"name": "Test Millet", "category": "CEREAL", "shelf_life_days": 200},
        expect=201,
    )
    assert data["name"] == "Test Millet"


def test_duplicate_crop_name_is_rejected(api):
    status, body = api.post("/api/crops", "admin", json={"name": "Tomato"})
    assert status == 409
