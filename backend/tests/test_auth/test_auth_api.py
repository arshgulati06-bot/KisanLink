"""Registration, login and session behaviour."""
import uuid


def _new_phone():
    """A phone number that passes validation and is unique per run."""
    return "9" + str(uuid.uuid4().int)[:9]


def test_register_farmer_returns_token_and_profile(api):
    phone = _new_phone()
    data = api.data(
        "post",
        "/api/auth/register",
        json={
            "name": "Test Farmer",
            "phone": phone,
            "password": "secret123",
            "role": "FARMER",
            "district": "Nashik",
            "village": "Ozar",
        },
        expect=201,
    )
    assert data["user"]["role"] == "FARMER"
    assert data["user"]["phone"] == phone
    assert data["profile"]["district"] == "Nashik"
    assert data["token"]


def test_password_hash_is_never_returned(api):
    data = api.data("get", "/api/auth/me", "farmer")
    assert "password_hash" not in data["user"]


def test_duplicate_phone_is_rejected(api):
    status, body = api.post(
        "/api/auth/register",
        json={
            "name": "Duplicate",
            "phone": "9000000002",
            "password": "secret123",
            "role": "FARMER",
        },
    )
    assert status == 409
    assert body["error"]["code"] == "CONFLICT"


def test_invalid_payload_lists_every_bad_field(api):
    status, body = api.post(
        "/api/auth/register",
        json={"name": "X", "phone": "12345", "password": "abc", "role": "WIZARD"},
    )
    assert status == 422
    details = body["error"]["details"]
    assert set(details) == {"name", "phone", "password", "role"}


def test_login_with_wrong_password_does_not_reveal_the_account(api):
    status, body = api.post(
        "/api/auth/login", json={"phone": "9000000002", "password": "wrong-password"}
    )
    unknown_status, unknown_body = api.post(
        "/api/auth/login", json={"phone": "9999999999", "password": "wrong-password"}
    )
    assert status == unknown_status == 401
    assert body["error"]["message"] == unknown_body["error"]["message"]


def test_protected_endpoint_requires_a_token(api):
    status, body = api.get("/api/auth/me")
    assert status == 401
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_garbage_token_is_rejected(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_buyer_registration_starts_unverified(api):
    data = api.data(
        "post",
        "/api/auth/register",
        json={
            "name": "New Buyer",
            "phone": _new_phone(),
            "password": "secret123",
            "role": "BUYER",
            "business_name": "New Buyer Foods",
            "buyer_type": "PROCESSOR",
        },
        expect=201,
    )
    # Signing up must never confer verification.
    assert data["profile"]["verification_status"] == "UNVERIFIED"
    assert data["profile"]["verification_label"] == "Not verified by the platform"


def test_change_password_requires_the_current_one(api):
    status, body = api.post(
        "/api/auth/change-password",
        "farmer2",
        json={"current_password": "not-it", "new_password": "brand-new-pass"},
    )
    assert status == 401
