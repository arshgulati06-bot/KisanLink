"""FPO membership and lot aggregation."""
import pytest


@pytest.fixture()
def fpo_id(api):
    return api.data("get", "/api/fpo")[0]["id"]


def test_fpo_detail_lists_its_members(api, fpo_id):
    data = api.data("get", f"/api/fpo/{fpo_id}")
    assert data["fpo_name"] == "Sahyadri Farmer Producer Company"
    assert len(data["members"]) >= 3
    assert all(member["farmer_name"] for member in data["members"])


def test_only_the_fpo_itself_can_manage_membership(api, fpo_id):
    status, _ = api.post(f"/api/fpo/{fpo_id}/members", "farmer", json={"phone": "9000000003"})
    assert status == 403


def test_a_member_can_be_added_by_phone_number(api, fpo_id):
    new_farmer = api.data(
        "post", "/api/auth/register",
        json={"name": "New Member", "phone": "9111100001", "password": "secret123",
              "role": "FARMER", "district": "Nashik"},
        expect=201,
    )
    members = api.data("post", f"/api/fpo/{fpo_id}/members", "fpo",
                       json={"phone": "9111100001"}, expect=201)
    assert any(m["farmer_phone"] == "9111100001" for m in members)
    assert new_farmer["user"]["name"] == "New Member"


def test_adding_an_unknown_number_fails_clearly(api, fpo_id):
    status, body = api.post(f"/api/fpo/{fpo_id}/members", "fpo", json={"phone": "9555500000"})
    assert status == 404
    assert "No account is registered" in body["error"]["message"]


def test_aggregation_needs_at_least_two_lots(api, fpo_id):
    crops = api.data("get", "/api/crops?q=Wheat")
    lot = api.data("post", "/api/lots", "farmer",
                   json={"crop_id": crops[0]["id"], "quantity": 20, "unit": "QUINTAL"},
                   expect=201)
    status, body = api.post(f"/api/fpo/{fpo_id}/aggregate", "fpo",
                            json={"lot_ids": [lot["id"]]})
    assert status == 422
    assert "at least 2 items" in body["error"]["details"]["lot_ids"]


def test_member_lots_pool_into_one_aggregated_lot(api, fpo_id):
    crops = api.data("get", "/api/crops?q=Jowar")
    crop_id = crops[0]["id"]
    lot_a = api.data("post", "/api/lots", "farmer",
                     json={"crop_id": crop_id, "quantity": 30, "unit": "QUINTAL", "grade": "A"},
                     expect=201)
    lot_b = api.data("post", "/api/lots", "farmer2",
                     json={"crop_id": crop_id, "quantity": 20, "unit": "QUINTAL", "grade": "B"},
                     expect=201)

    candidates = api.data("get", f"/api/fpo/{fpo_id}/aggregation-candidates?crop_id={crop_id}",
                          "fpo")
    candidate_ids = {lot["id"] for lot in candidates["candidate_lots"]}
    assert {lot_a["id"], lot_b["id"]} <= candidate_ids

    result = api.data("post", f"/api/fpo/{fpo_id}/aggregate", "fpo",
                      json={"lot_ids": [lot_a["id"], lot_b["id"]], "expected_price": 2400},
                      expect=201)
    aggregate = result["aggregated_lot"]
    assert aggregate["quantity"] == 50
    assert aggregate["is_aggregated"] is True
    # A pooled consignment can only honestly be sold at its weakest grade.
    assert aggregate["grade"] == "B"

    contributions = result["contributions"]
    assert sorted(c["quantity"] for c in contributions) == [20, 30]
    assert all(c["farmer_name"] for c in contributions)

    # The source lots are consumed, not left as duplicate supply.
    assert api.data("get", f"/api/lots/{lot_a['id']}")["status"] == "CANCELLED"


def test_lots_of_different_crops_cannot_be_pooled(api, fpo_id):
    wheat = api.data("get", "/api/crops?q=Wheat")[0]["id"]
    bajra = api.data("get", "/api/crops?q=Bajra")[0]["id"]
    lot_a = api.data("post", "/api/lots", "farmer",
                     json={"crop_id": wheat, "quantity": 10, "unit": "QUINTAL"}, expect=201)
    lot_b = api.data("post", "/api/lots", "farmer2",
                     json={"crop_id": bajra, "quantity": 10, "unit": "QUINTAL"}, expect=201)
    status, body = api.post(f"/api/fpo/{fpo_id}/aggregate", "fpo",
                            json={"lot_ids": [lot_a["id"], lot_b["id"]]})
    assert status == 422
    assert "same crop" in body["error"]["message"]


def test_a_lot_under_negotiation_is_never_swept_into_a_pool(api, fpo_id):
    crops = api.data("get", "/api/crops?q=Gram")
    crop_id = crops[0]["id"]
    lot = api.data("post", "/api/lots", "farmer",
                   json={"crop_id": crop_id, "quantity": 15, "unit": "QUINTAL"}, expect=201)
    api.data("post", f"/api/lots/{lot['id']}/publish", "farmer")
    api.data("post", "/api/offers", "processor",
             json={"lot_id": lot["id"], "price_per_unit": 5000}, expect=201)

    candidates = api.data("get", f"/api/fpo/{fpo_id}/aggregation-candidates?crop_id={crop_id}",
                          "fpo")
    assert lot["id"] not in {c["id"] for c in candidates["candidate_lots"]}


def test_payout_split_is_recorded_pro_rata(api, fpo_id):
    from app.repositories.lot_repository import lot_contribution_repository

    crops = api.data("get", "/api/crops?q=Turmeric")
    crop_id = crops[0]["id"]
    lot_a = api.data("post", "/api/lots", "farmer",
                     json={"crop_id": crop_id, "quantity": 75, "unit": "QUINTAL"}, expect=201)
    lot_b = api.data("post", "/api/lots", "farmer2",
                     json={"crop_id": crop_id, "quantity": 25, "unit": "QUINTAL"}, expect=201)
    result = api.data("post", f"/api/fpo/{fpo_id}/aggregate", "fpo",
                      json={"lot_ids": [lot_a["id"], lot_b["id"]]}, expect=201)
    aggregate_id = result["aggregated_lot"]["id"]

    payouts = lot_contribution_repository.record_payouts(aggregate_id, 100000)
    amounts = sorted(payout["payout_amount"] for payout in payouts)
    assert amounts == [25000.0, 75000.0]
    # Rounding must never lose or invent rupees.
    assert sum(amounts) == 100000.0
