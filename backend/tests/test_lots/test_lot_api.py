"""Lot creation, publishing and edit rules."""


def test_farmer_can_create_and_publish_a_lot(api, own_lot):
    assert own_lot["status"] == "DRAFT"
    published = api.data("post", f"/api/lots/{own_lot['id']}/publish", "farmer")
    assert published["status"] == "LISTED"


def test_lot_inherits_location_from_the_farmer_profile(api, tomato_crop_id):
    lot = api.data(
        "post",
        "/api/lots",
        "farmer",
        json={"crop_id": tomato_crop_id, "quantity": 5, "unit": "QUINTAL", "grade": "A"},
        expect=201,
    )
    # Ramesh Patil's profile is in Ozar, Nashik.
    assert lot["district"] == "Nashik"
    assert lot["latitude"] is not None


def test_lot_gets_a_human_readable_code(api, own_lot):
    assert own_lot["lot_code"].startswith("LOT")


def test_buyers_cannot_create_lots(api, tomato_crop_id):
    status, body = api.post(
        "/api/lots", "processor", json={"crop_id": tomato_crop_id, "quantity": 10}
    )
    assert status == 403
    assert body["error"]["code"] == "FORBIDDEN"


def test_a_farmer_cannot_edit_another_farmers_lot(api, listed_tomato_lot):
    status, _ = api.put(
        f"/api/lots/{listed_tomato_lot['id']}", "farmer3", json={"expected_price": 1}
    )
    assert status == 403


def test_quantity_must_be_positive(api, tomato_crop_id):
    status, body = api.post(
        "/api/lots", "farmer", json={"crop_id": tomato_crop_id, "quantity": 0}
    )
    assert status == 422
    assert "quantity" in body["error"]["details"]


def test_availability_window_must_be_ordered(api, tomato_crop_id):
    status, body = api.post(
        "/api/lots",
        "farmer",
        json={
            "crop_id": tomato_crop_id,
            "quantity": 10,
            "available_from": "2026-05-10",
            "available_until": "2026-05-01",
        },
    )
    assert status == 422
    assert "available_until" in body["error"]["message"]


def test_public_listing_hides_drafts(api, own_lot):
    """A draft is the farmer's private working copy, not supply on the market."""
    public = api.data("get", "/api/lots")
    assert own_lot["id"] not in [lot["id"] for lot in public]
    mine = api.data("get", "/api/lots?mine=true", "farmer")
    assert own_lot["id"] in [lot["id"] for lot in mine]


def test_only_draft_lots_can_be_deleted(api, own_lot):
    api.data("post", f"/api/lots/{own_lot['id']}/publish", "farmer")
    status, body = api.delete(f"/api/lots/{own_lot['id']}", "farmer")
    assert status == 409
    assert "Withdraw" in body["error"]["message"]


def test_withdrawn_lot_keeps_its_record(api, own_lot):
    api.data("post", f"/api/lots/{own_lot['id']}/publish", "farmer")
    withdrawn = api.data(
        "post", f"/api/lots/{own_lot['id']}/withdraw", "farmer", json={"reason": "Sold locally."}
    )
    assert withdrawn["status"] == "CANCELLED"
    assert api.data("get", f"/api/lots/{own_lot['id']}")["id"] == own_lot["id"]


def test_seller_dashboard_summarises_activity(api):
    data = api.data("get", "/api/lots/dashboard", "farmer")
    assert "summary" in data
    assert data["summary"]["total_lots"] >= 1
