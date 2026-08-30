"""Offers, counter-offers and acceptance."""
import pytest


@pytest.fixture()
def open_lot(api):
    """A published lot of this farmer's own, free for a test to negotiate on."""
    crops = api.data("get", "/api/crops?q=Tomato")
    lot = api.data(
        "post",
        "/api/lots",
        "farmer2",
        json={
            "crop_id": crops[0]["id"],
            "quantity": 40,
            "unit": "QUINTAL",
            "grade": "A",
            "expected_price": 2700,
            "district": "Nashik",
            "latitude": 20.08,
            "longitude": 74.11,
        },
        expect=201,
    )
    return api.data("post", f"/api/lots/{lot['id']}/publish", "farmer2")


def test_buyer_can_offer_on_a_listed_lot(api, open_lot):
    offer = api.data(
        "post",
        "/api/offers",
        "processor",
        json={"lot_id": open_lot["id"], "price_per_unit": 2750, "quantity": 40},
        expect=201,
    )
    assert offer["status"] == "PENDING"
    assert offer["gross_amount"] == 110000
    assert api.data("get", f"/api/lots/{open_lot['id']}")["status"] == "OFFER_RECEIVED"


def test_a_buyer_may_hold_only_one_live_offer_per_lot(api, open_lot):
    api.data("post", "/api/offers", "processor",
             json={"lot_id": open_lot["id"], "price_per_unit": 2700}, expect=201)
    status, body = api.post("/api/offers", "processor",
                            json={"lot_id": open_lot["id"], "price_per_unit": 2800})
    assert status == 409
    assert "Withdraw it" in body["error"]["message"]


def test_offer_cannot_exceed_the_lot_quantity(api, open_lot):
    status, body = api.post(
        "/api/offers", "processor",
        json={"lot_id": open_lot["id"], "price_per_unit": 2700, "quantity": 500},
    )
    assert status == 422
    assert "exceeds the lot size" in body["error"]["message"]


def test_a_farmer_cannot_offer_on_their_own_lot(api, open_lot):
    status, _ = api.post("/api/offers", "farmer2",
                         json={"lot_id": open_lot["id"], "price_per_unit": 2700})
    assert status == 403  # farmers have no buyer profile at all


def test_farmer_can_counter_and_the_buyer_answers(api, open_lot):
    offer = api.data("post", "/api/offers", "processor",
                     json={"lot_id": open_lot["id"], "price_per_unit": 2600}, expect=201)
    counter = api.data("post", f"/api/offers/{offer['id']}/counter", "farmer2",
                       json={"price_per_unit": 2850, "message": "Grade A."}, expect=201)
    assert counter["initiated_by"] == "FARMER"
    assert counter["parent_offer_id"] == offer["id"]
    assert api.data("get", f"/api/offers/{offer['id']}", "farmer2")["status"] == "COUNTERED"

    # The counter is addressed to the buyer, so only they can accept it.
    status, _ = api.post(f"/api/offers/{counter['id']}/accept", "farmer2")
    assert status == 403
    result = api.data("post", f"/api/offers/{counter['id']}/accept", "processor")
    assert result["offer"]["status"] == "ACCEPTED"


def test_accepting_closes_the_lot_and_rejects_rival_offers(api, open_lot):
    first = api.data("post", "/api/offers", "processor",
                     json={"lot_id": open_lot["id"], "price_per_unit": 2700}, expect=201)
    rival = api.data("post", "/api/offers", "aggregator",
                     json={"lot_id": open_lot["id"], "price_per_unit": 2650}, expect=201)

    api.data("post", f"/api/offers/{first['id']}/accept", "farmer2")

    assert api.data("get", f"/api/lots/{open_lot['id']}")["status"] == "SOLD"
    assert api.data("get", f"/api/offers/{rival['id']}", "farmer2")["status"] == "REJECTED"


def test_no_offers_are_accepted_on_a_sold_lot(api, open_lot):
    offer = api.data("post", "/api/offers", "processor",
                     json={"lot_id": open_lot["id"], "price_per_unit": 2700}, expect=201)
    api.data("post", f"/api/offers/{offer['id']}/accept", "farmer2")
    status, body = api.post("/api/offers", "aggregator",
                            json={"lot_id": open_lot["id"], "price_per_unit": 3000})
    assert status == 409
    assert "not accepting offers" in body["error"]["message"]


def test_withdrawing_the_last_offer_relists_the_lot(api, open_lot):
    offer = api.data("post", "/api/offers", "processor",
                     json={"lot_id": open_lot["id"], "price_per_unit": 2700}, expect=201)
    assert api.data("get", f"/api/lots/{open_lot['id']}")["status"] == "OFFER_RECEIVED"
    api.data("post", f"/api/offers/{offer['id']}/withdraw", "processor")
    assert api.data("get", f"/api/lots/{open_lot['id']}")["status"] == "LISTED"


def test_only_the_issuing_buyer_can_withdraw(api, open_lot):
    offer = api.data("post", "/api/offers", "processor",
                     json={"lot_id": open_lot["id"], "price_per_unit": 2700}, expect=201)
    status, _ = api.post(f"/api/offers/{offer['id']}/withdraw", "aggregator")
    assert status == 403


def test_offer_lists_are_scoped_to_the_caller(api, open_lot):
    api.data("post", "/api/offers", "processor",
             json={"lot_id": open_lot["id"], "price_per_unit": 2700}, expect=201)
    buyer_view = api.data("get", "/api/offers", "processor")
    seller_view = api.data("get", "/api/offers", "farmer2")
    assert all(offer["business_name"] == "ABC Foods Processing Pvt Ltd" for offer in buyer_view)
    assert all(offer["seller_name"] == "Sunita Jadhav" for offer in seller_view)


def test_a_third_party_cannot_read_all_offers_on_someone_elses_lot(api, open_lot):
    api.data("post", "/api/offers", "processor",
             json={"lot_id": open_lot["id"], "price_per_unit": 2700}, expect=201)
    status, _ = api.get(f"/api/offers/lot/{open_lot['id']}", "farmer3")
    assert status == 403
