"""Transaction lifecycle, the status trail and payment tracking."""
import pytest


@pytest.fixture()
def accepted_transaction(api):
    """A fresh lot taken all the way to an accepted offer."""
    crops = api.data("get", "/api/crops?q=Onion")
    lot = api.data(
        "post", "/api/lots", "farmer3",
        json={
            "crop_id": crops[0]["id"], "quantity": 30, "unit": "QUINTAL", "grade": "B",
            "expected_price": 1800, "district": "Ahmednagar",
            "latitude": 19.39, "longitude": 74.65,
        },
        expect=201,
    )
    api.data("post", f"/api/lots/{lot['id']}/publish", "farmer3")
    offer = api.data(
        "post", "/api/offers", "processor",
        json={"lot_id": lot["id"], "price_per_unit": 1850, "quantity": 30,
              "payment_terms_days": 7},
        expect=201,
    )
    result = api.data("post", f"/api/offers/{offer['id']}/accept", "farmer3")
    return result["transaction"]


def test_accepting_an_offer_opens_a_transaction(accepted_transaction):
    txn = accepted_transaction
    assert txn["status"] == "ACCEPTED"
    assert txn["transaction_code"].startswith("TXN")
    assert txn["gross_amount"] == pytest.approx(1850 * 30)


def test_gross_and_net_are_recorded_separately(accepted_transaction):
    """The record must never let the headline price read as what the farmer got."""
    txn = accepted_transaction
    assert txn["net_amount"] < txn["gross_amount"]
    assert txn["transport_cost"] > 0
    assert txn["net_amount"] == pytest.approx(
        txn["gross_amount"] - txn["transport_cost"] - txn["commission_cost"], abs=0.02
    )


def test_realization_breakdown_shows_the_arithmetic(api, accepted_transaction):
    data = api.data("get", f"/api/transactions/{accepted_transaction['id']}/realization", "farmer3")
    assert data["gross_amount"] - data["total_deductions"] == pytest.approx(data["net_amount"])
    assert data["net_price_per_unit"] < data["gross_price_per_unit"]
    assert "estimates" in data["note"]


def test_status_moves_are_restricted_to_the_defined_flow(api, accepted_transaction):
    txn_id = accepted_transaction["id"]
    status, body = api.put(f"/api/transactions/{txn_id}/status", "farmer3",
                           json={"status": "COMPLETED"})
    assert status == 409
    assert "Allowed next steps" in body["error"]["message"]


def test_the_full_status_path_is_recorded_with_who_changed_it(api, accepted_transaction):
    txn_id = accepted_transaction["id"]
    for step in ("LOGISTICS_PENDING", "IN_TRANSIT", "DELIVERED"):
        api.data("put", f"/api/transactions/{txn_id}/status", "farmer3",
                 json={"status": step, "remarks": f"moved to {step}"})
    history = api.data("get", f"/api/transactions/{txn_id}/history", "farmer3")
    assert [entry["to_status"] for entry in history] == [
        "ACCEPTED", "LOGISTICS_PENDING", "IN_TRANSIT", "DELIVERED"
    ]
    assert all(entry["changed_by_name"] for entry in history)
    assert all(entry["created_at"] for entry in history)


def test_a_full_payment_settles_the_transaction(api, accepted_transaction):
    txn_id = accepted_transaction["id"]
    for step in ("LOGISTICS_PENDING", "IN_TRANSIT", "DELIVERED"):
        api.data("put", f"/api/transactions/{txn_id}/status", "farmer3", json={"status": step})

    api.data("post", f"/api/transactions/{txn_id}/payments", "processor",
             json={"amount": accepted_transaction["gross_amount"], "mode": "UPI",
                   "reference_no": "TESTUPI1"}, expect=201)

    detail = api.data("get", f"/api/transactions/{txn_id}", "farmer3")
    assert detail["status"] == "PAID"
    assert detail["amount_outstanding"] == 0


def test_a_part_payment_leaves_the_balance_outstanding(api, accepted_transaction):
    """The obligation raised at acceptance must be settled, not duplicated."""
    txn_id = accepted_transaction["id"]
    gross = accepted_transaction["gross_amount"]
    for step in ("LOGISTICS_PENDING", "IN_TRANSIT", "DELIVERED"):
        api.data("put", f"/api/transactions/{txn_id}/status", "farmer3", json={"status": step})

    api.data("post", f"/api/transactions/{txn_id}/payments", "processor",
             json={"amount": 20000}, expect=201)
    detail = api.data("get", f"/api/transactions/{txn_id}", "farmer3")
    assert detail["amount_outstanding"] == pytest.approx(gross - 20000)
    assert detail["status"] == "DELIVERED"

    api.data("post", f"/api/transactions/{txn_id}/payments", "processor",
             json={"amount": gross - 20000}, expect=201)
    detail = api.data("get", f"/api/transactions/{txn_id}", "farmer3")
    assert detail["amount_outstanding"] == 0
    assert detail["status"] == "PAID"


def test_overpayment_is_refused(api, accepted_transaction):
    txn_id = accepted_transaction["id"]
    status, body = api.post(
        f"/api/transactions/{txn_id}/payments", "processor",
        json={"amount": accepted_transaction["gross_amount"] * 2},
    )
    assert status == 422
    assert "exceed the transaction value" in body["error"]["message"]


def test_outsiders_cannot_read_a_transaction(api, accepted_transaction):
    status, body = api.get(f"/api/transactions/{accepted_transaction['id']}", "farmer")
    assert status == 403
    assert body["error"]["code"] == "FORBIDDEN"


def test_both_parties_can_read_their_own_transaction(api, accepted_transaction):
    txn_id = accepted_transaction["id"]
    seller = api.data("get", f"/api/transactions/{txn_id}", "farmer3")
    buyer = api.data("get", f"/api/transactions/{txn_id}", "processor")
    assert seller["is_seller"] is True
    assert buyer["is_seller"] is False


def test_transaction_lists_are_scoped_by_role(api, accepted_transaction):
    seller_view = api.data("get", "/api/transactions", "farmer3")
    assert all(txn["seller_name"] == "Vitthal Shinde" for txn in seller_view)
    buyer_view = api.data("get", "/api/transactions", "processor")
    assert all(txn["business_name"] == "ABC Foods Processing Pvt Ltd" for txn in buyer_view)
