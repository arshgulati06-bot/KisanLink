"""Verification, trust scoring, ratings and grievances."""
import pytest


@pytest.fixture()
def completed_transaction(api):
    """A deal taken all the way to COMPLETED so it can be rated and disputed."""
    crops = api.data("get", "/api/crops?q=Cotton")
    lot = api.data("post", "/api/lots", "farmer",
                   json={"crop_id": crops[0]["id"], "quantity": 20, "unit": "QUINTAL",
                         "grade": "A", "district": "Nashik"}, expect=201)
    api.data("post", f"/api/lots/{lot['id']}/publish", "farmer")
    offer = api.data("post", "/api/offers", "institutional",
                     json={"lot_id": lot["id"], "price_per_unit": 7200, "quantity": 20},
                     expect=201)
    txn = api.data("post", f"/api/offers/{offer['id']}/accept", "farmer")["transaction"]
    for step in ("LOGISTICS_PENDING", "IN_TRANSIT", "DELIVERED"):
        api.data("put", f"/api/transactions/{txn['id']}/status", "farmer", json={"status": step})
    api.data("post", f"/api/transactions/{txn['id']}/payments", "institutional",
             json={"amount": txn["gross_amount"], "mode": "BANK_TRANSFER"}, expect=201)
    api.data("put", f"/api/transactions/{txn['id']}/status", "farmer",
             json={"status": "COMPLETED"})
    return txn


# --- trust scoring ---------------------------------------------------------
def test_trust_score_shows_its_components(api):
    buyers = api.data("get", "/api/buyers?page_size=1")
    data = api.data("get", f"/api/trust/buyers/{buyers[0]['id']}")
    assert 0 <= data["trust_score"] <= 100
    assert set(data["components"]) == {
        "verification", "ratings", "completed_transactions",
        "payment_punctuality", "grievance_penalty",
    }
    assert all(part["detail"] for part in data["components"].values())


def test_trust_score_carries_the_verification_disclaimer(api):
    buyers = api.data("get", "/api/buyers?page_size=1")
    data = api.data("get", f"/api/trust/buyers/{buyers[0]['id']}")
    assert "not a government KYC" in data["disclaimer"]


def test_an_unproven_buyer_is_marked_provisional_not_untrustworthy(api):
    buyers = api.data("get", "/api/buyers?verification_status=UNVERIFIED")
    if not buyers:
        pytest.skip("no unverified buyer in the demo data")
    data = api.data("get", f"/api/trust/buyers/{buyers[0]['id']}")
    assert data["is_provisional"] is True
    assert "provisional" in data["note"]


def test_a_reviewed_buyer_scores_above_an_unverified_one(api):
    reviewed = api.data("get", "/api/buyers?verification_status=PLATFORM_REVIEWED")
    unverified = api.data("get", "/api/buyers?verification_status=UNVERIFIED")
    if not reviewed or not unverified:
        pytest.skip("demo data does not contain both verification states")
    high = api.data("get", f"/api/trust/buyers/{reviewed[0]['id']}")["trust_score"]
    low = api.data("get", f"/api/trust/buyers/{unverified[0]['id']}")["trust_score"]
    assert high > low


# --- verification ----------------------------------------------------------
def test_only_an_admin_can_verify_a_buyer(api):
    buyers = api.data("get", "/api/buyers?page_size=1")
    status, _ = api.put(f"/api/trust/buyers/{buyers[0]['id']}/verify", "processor",
                        json={"verification_status": "PLATFORM_REVIEWED", "notes": "self"})
    assert status == 403


def test_marking_a_buyer_reviewed_requires_a_written_reason(api):
    buyers = api.data("get", "/api/buyers?verification_status=UNVERIFIED")
    if not buyers:
        pytest.skip("no unverified buyer in the demo data")
    status, body = api.put(f"/api/trust/buyers/{buyers[0]['id']}/verify", "admin",
                           json={"verification_status": "PLATFORM_REVIEWED"})
    assert status == 422
    assert "Record what was reviewed" in body["error"]["message"]


def test_admin_verification_updates_status_and_score(api):
    buyers = api.data("get", "/api/buyers?verification_status=DOCUMENTS_SUBMITTED")
    if not buyers:
        pytest.skip("no buyer awaiting review in the demo data")
    buyer_id = buyers[0]["id"]
    before = api.data("get", f"/api/trust/buyers/{buyer_id}")["trust_score"]
    updated = api.data("put", f"/api/trust/buyers/{buyer_id}/verify", "admin",
                       json={"verification_status": "PLATFORM_REVIEWED",
                             "notes": "GST and licence checked against submitted documents."})
    assert updated["verification_status"] == "PLATFORM_REVIEWED"
    assert api.data("get", f"/api/trust/buyers/{buyer_id}")["trust_score"] > before


# --- ratings ---------------------------------------------------------------
def test_a_completed_deal_can_be_rated_once(api, completed_transaction):
    api.data("post", "/api/trust/ratings", "farmer",
             json={"transaction_id": completed_transaction["id"], "score": 4.5,
                   "payment_score": 5, "comment": "Paid on time."}, expect=201)
    status, body = api.post("/api/trust/ratings", "farmer",
                            json={"transaction_id": completed_transaction["id"], "score": 3})
    assert status == 409
    assert "already rated" in body["error"]["message"]


def test_only_a_party_to_the_deal_can_rate_it(api, completed_transaction):
    status, _ = api.post("/api/trust/ratings", "farmer3",
                         json={"transaction_id": completed_transaction["id"], "score": 1})
    assert status == 403


def test_ratings_are_bounded(api, completed_transaction):
    status, body = api.post("/api/trust/ratings", "institutional",
                            json={"transaction_id": completed_transaction["id"], "score": 9})
    assert status == 422
    assert "score" in body["error"]["details"]


def test_an_unfinished_deal_cannot_be_rated(api):
    crops = api.data("get", "/api/crops?q=Bajra")
    lot = api.data("post", "/api/lots", "farmer2",
                   json={"crop_id": crops[0]["id"], "quantity": 10, "unit": "QUINTAL"},
                   expect=201)
    api.data("post", f"/api/lots/{lot['id']}/publish", "farmer2")
    offer = api.data("post", "/api/offers", "processor",
                     json={"lot_id": lot["id"], "price_per_unit": 2400}, expect=201)
    txn = api.data("post", f"/api/offers/{offer['id']}/accept", "farmer2")["transaction"]
    status, body = api.post("/api/trust/ratings", "farmer2",
                            json={"transaction_id": txn["id"], "score": 5})
    assert status == 409
    assert "paid or completed" in body["error"]["message"]


# --- grievances ------------------------------------------------------------
def test_a_grievance_gets_a_ticket_and_names_the_other_party(api, completed_transaction):
    data = api.data("post", "/api/grievances", "farmer",
                    json={"transaction_id": completed_transaction["id"],
                          "category": "PAYMENT_DELAY",
                          "subject": "Payment received late",
                          "description": "The payment arrived four days after the due date."},
                    expect=201)
    assert data["ticket_no"].startswith("GRV")
    assert data["status"] == "OPEN"
    # The respondent is inferred from the transaction rather than asked for.
    assert data["against_name"] == "Priya Menon"


def test_a_complainant_cannot_resolve_their_own_grievance(api, completed_transaction):
    grievance = api.data("post", "/api/grievances", "farmer",
                         json={"transaction_id": completed_transaction["id"],
                               "subject": "Quality dispute raised",
                               "description": "The buyer disputed the grade after delivery."},
                         expect=201)
    status, _ = api.put(f"/api/grievances/{grievance['id']}", "farmer",
                        json={"status": "RESOLVED", "resolution": "closing it myself"})
    assert status == 403


def test_a_complainant_may_withdraw_their_own_grievance(api, completed_transaction):
    grievance = api.data("post", "/api/grievances", "farmer",
                         json={"transaction_id": completed_transaction["id"],
                               "subject": "Raised in error",
                               "description": "This was recorded by mistake and is withdrawn."},
                         expect=201)
    data = api.data("put", f"/api/grievances/{grievance['id']}", "farmer",
                    json={"status": "WITHDRAWN"})
    assert data["status"] == "WITHDRAWN"


def test_closing_a_grievance_requires_a_resolution(api, completed_transaction):
    grievance = api.data("post", "/api/grievances", "farmer",
                         json={"transaction_id": completed_transaction["id"],
                               "subject": "Short weight on delivery",
                               "description": "Delivered weight was below the agreed quantity."},
                         expect=201)
    status, body = api.put(f"/api/grievances/{grievance['id']}", "admin",
                           json={"status": "RESOLVED"})
    assert status == 422
    assert "resolution" in body["error"]["message"]

    resolved = api.data("put", f"/api/grievances/{grievance['id']}", "admin",
                        json={"status": "RESOLVED",
                              "resolution": "Weighbridge slip verified; difference settled."})
    assert resolved["status"] == "RESOLVED"
    assert resolved["resolved_at"]
    assert resolved["handled_by_name"] == "Platform Administrator"


def test_an_open_grievance_lowers_the_trust_score(api, completed_transaction):
    buyer_id = api.data("get", "/api/buyers?q=Statewide")[0]["id"]
    before = api.data("get", f"/api/trust/buyers/{buyer_id}")["trust_score"]
    api.data("post", "/api/grievances", "farmer",
             json={"transaction_id": completed_transaction["id"],
                   "category": "PAYMENT_DELAY",
                   "subject": "Repeated payment delay",
                   "description": "Payment for this consignment is again overdue."},
             expect=201)
    after = api.data("get", f"/api/trust/buyers/{buyer_id}")
    assert after["open_grievances"] >= 1
    assert after["trust_score"] < before
    assert after["components"]["grievance_penalty"]["points"] < 0


def test_grievances_are_private_to_the_parties(api, completed_transaction):
    grievance = api.data("post", "/api/grievances", "farmer",
                         json={"transaction_id": completed_transaction["id"],
                               "subject": "Private matter between the parties",
                               "description": "Details of a dispute that no one else may read."},
                         expect=201)
    status, _ = api.get(f"/api/grievances/{grievance['id']}", "farmer3")
    assert status == 403
    api.data("get", f"/api/grievances/{grievance['id']}", "admin")


def test_status_flow_is_enforced_on_grievances(api, completed_transaction):
    grievance = api.data("post", "/api/grievances", "farmer",
                         json={"transaction_id": completed_transaction["id"],
                               "subject": "Flow check on grievance status",
                               "description": "Used to confirm a closed ticket cannot reopen."},
                         expect=201)
    api.data("put", f"/api/grievances/{grievance['id']}", "admin",
             json={"status": "REJECTED", "resolution": "Not substantiated."})
    status, body = api.put(f"/api/grievances/{grievance['id']}", "admin",
                           json={"status": "UNDER_REVIEW"})
    assert status == 409
    assert "cannot move to" in body["error"]["message"]
