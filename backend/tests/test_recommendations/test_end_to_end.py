"""
The critical demo path, start to finish.

This is the flow the project documentation names as the one that must work
before anything else is added:

    farmer login -> create lot -> market intelligence -> buyer matching
    -> net realization -> best opportunity -> why? -> buyer offer
    -> farmer accepts -> transaction status

If this test fails, the demo fails.
"""
import pytest


def test_farm_gate_to_payment(api):
    # 1. The farmer signs in.
    profile = api.data("get", "/api/auth/me", "farmer")
    assert profile["user"]["role"] == "FARMER"

    crop_id = api.data("get", "/api/crops?q=Tomato")[0]["id"]

    # 2. Creates and publishes a 1000 kg Grade A tomato lot.
    lot = api.data(
        "post", "/api/lots", "farmer",
        json={"crop_id": crop_id, "quantity": 1000, "unit": "KG", "grade": "A",
              "moisture_percent": 8.5, "expected_price": 28,
              "village": "Ozar", "district": "Nashik",
              "latitude": 20.05, "longitude": 73.85},
        expect=201,
    )
    lot = api.data("post", f"/api/lots/{lot['id']}/publish", "farmer")
    assert lot["status"] == "LISTED"

    # 3. Market intelligence: several markets, with a spread worth acting on.
    intelligence = api.data("get", f"/api/prices/overview?crop_id={crop_id}&district=Nashik")
    assert intelligence["markets_reporting"] >= 2
    assert intelligence["price_spread"] > 0

    # 4. Buyer matching returns more than one option, each explained.
    matches = api.data("get", f"/api/lots/{lot['id']}/matches", "farmer")
    assert len(matches["matches"]) >= 2
    assert all(match["score_components"]["price"]["reason"] for match in matches["matches"])

    # 5. The recommendation costs every channel down to a net realization.
    recommendation = api.data("get", f"/api/lots/{lot['id']}/recommendation", "farmer")
    best = recommendation["recommended_option"]
    assert best["net_price_per_unit"] <= best["gross_price_per_unit"]
    assert best["realization"]["net_amount"] > 0

    # 6. ...ranks them...
    comparison = recommendation["comparison"]
    assert [row["rank"] for row in comparison] == sorted(row["rank"] for row in comparison)
    assert len({row["option_type"] for row in comparison}) >= 2

    # 7. ...explains why, and answers the timing question.
    assert len(recommendation["why_this_recommendation"]) >= 4
    assert recommendation["sale_window"]["recommendation"] in (
        "SELL_NOW", "CONSIDER_WAITING", "MONITOR", "INSUFFICIENT_DATA"
    )
    assert recommendation["sale_window"]["reasons"]

    # 8. A buyer makes a digital offer.
    offer = api.data(
        "post", "/api/offers", "processor",
        json={"lot_id": lot["id"], "price_per_unit": 28.5, "quantity": 1000, "unit": "KG",
              "payment_terms_days": 7, "message": "Delivered at Ranjangaon."},
        expect=201,
    )
    assert offer["status"] == "PENDING"

    # 9. The farmer counters and the buyer accepts.
    counter = api.data("post", f"/api/offers/{offer['id']}/counter", "farmer",
                       json={"price_per_unit": 29.5}, expect=201)
    accepted = api.data("post", f"/api/offers/{counter['id']}/accept", "processor")
    transaction = accepted["transaction"]
    assert transaction["gross_amount"] == pytest.approx(29.5 * 1000)
    assert api.data("get", f"/api/lots/{lot['id']}")["status"] == "SOLD"

    # 10. The transaction is tracked through to payment, with a full trail.
    txn_id = transaction["id"]
    for step in ("LOGISTICS_PENDING", "IN_TRANSIT", "DELIVERED"):
        api.data("put", f"/api/transactions/{txn_id}/status", "farmer", json={"status": step})
    api.data("post", f"/api/transactions/{txn_id}/payments", "processor",
             json={"amount": transaction["gross_amount"], "mode": "UPI",
                   "reference_no": "E2EUPI001"}, expect=201)
    api.data("put", f"/api/transactions/{txn_id}/status", "farmer",
             json={"status": "COMPLETED", "remarks": "Deal closed."})

    final = api.data("get", f"/api/transactions/{txn_id}", "farmer")
    assert final["status"] == "COMPLETED"
    assert final["amount_outstanding"] == 0
    assert [entry["to_status"] for entry in final["history"]] == [
        "ACCEPTED", "LOGISTICS_PENDING", "IN_TRANSIT", "DELIVERED",
        "PAYMENT_PENDING", "PAID", "COMPLETED",
    ]

    # 11. The record shows what the farmer actually realised, not the headline.
    realization = api.data("get", f"/api/transactions/{txn_id}/realization", "farmer")
    assert realization["gross_price_per_unit"] == 29.5
    assert realization["net_price_per_unit"] < realization["gross_price_per_unit"]
