"""
Shared test fixtures.

The suite runs against a throwaway SQLite database built from the real
``database/schema.sql``, ``seed.sql`` and ``test_data.sql``. That means the
tests exercise the same SQL the MySQL deployment uses, and a mistake in the
schema or the seed data fails here rather than in the demo.

Environment variables are set before any application module is imported,
because settings are read at import time.
"""
import os
import tempfile

os.environ.setdefault("DB_BACKEND", "sqlite")
os.environ.setdefault("DB_ALLOW_SQLITE_FALLBACK", "true")
os.environ["SQLITE_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="kisanlink-tests-"), "test.sqlite3"
)
os.environ.setdefault("SECRET_KEY", "kisanlink-test-secret-key-not-for-production-use")

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.config import db  # noqa: E402

#: Every demo account in ``database/test_data.sql`` shares this password.
DEMO_PASSWORD = "Kisan@123"

PHONES = {
    "admin": "9000000001",
    "farmer": "9000000002",
    "farmer2": "9000000003",
    "farmer3": "9000000004",
    "fpo": "9000000005",
    "processor": "9000000010",
    "institutional": "9000000011",
    "aggregator": "9000000012",
    "trader": "9000000013",
}


@pytest.fixture(scope="session")
def app():
    """A Flask app backed by a freshly built demo database."""
    db.reset_backend()
    db.init_schema()
    db.load_seed_data("seed.sql")
    db.load_seed_data("test_data.sql")
    application = create_app({"TESTING": True})
    yield application
    db.close_connection()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def api(client):
    """
    A thin wrapper that unwraps the response envelope.

    Every helper returns ``(status_code, body)`` so a test can assert on both
    without repeating ``resp.get_json()`` everywhere.
    """

    class Api:
        def __init__(self, test_client):
            self.client = test_client
            self._tokens = {}

        def token(self, who):
            if who not in self._tokens:
                response = self.client.post(
                    "/api/auth/login",
                    json={"phone": PHONES[who], "password": DEMO_PASSWORD},
                )
                assert response.status_code == 200, response.get_json()
                self._tokens[who] = response.get_json()["data"]["token"]
            return self._tokens[who]

        def headers(self, who=None):
            return {"Authorization": f"Bearer {self.token(who)}"} if who else {}

        def request(self, method, url, who=None, **kwargs):
            response = getattr(self.client, method)(
                url, headers=self.headers(who), **kwargs
            )
            return response.status_code, response.get_json()

        def get(self, url, who=None, **kwargs):
            return self.request("get", url, who, **kwargs)

        def post(self, url, who=None, **kwargs):
            return self.request("post", url, who, **kwargs)

        def put(self, url, who=None, **kwargs):
            return self.request("put", url, who, **kwargs)

        def delete(self, url, who=None, **kwargs):
            return self.request("delete", url, who, **kwargs)

        def data(self, method, url, who=None, expect=(200, 201), **kwargs):
            """Call an endpoint, assert it succeeded, and return just the data."""
            status, body = self.request(method, url, who, **kwargs)
            assert status in (expect if isinstance(expect, tuple) else (expect,)), (
                f"{method.upper()} {url} -> {status}: {body}"
            )
            return body["data"]

    return Api(client)


@pytest.fixture()
def tomato_crop_id(api):
    crops = api.data("get", "/api/crops?q=Tomato")
    return crops[0]["id"]


@pytest.fixture()
def listed_tomato_lot(api, tomato_crop_id):
    """The 1000 kg Grade A tomato lot from the demo scenario."""
    lots = api.data("get", f"/api/lots?crop_id={tomato_crop_id}")
    listed = [lot for lot in lots if lot["status"] in ("LISTED", "OFFER_RECEIVED")]
    assert listed, "the demo scenario should contain at least one listed tomato lot"
    return max(listed, key=lambda lot: lot["quantity"])


@pytest.fixture()
def own_lot(api):
    """
    A fresh, privately created lot each test can mutate freely.

    Tests that change a lot's state must not fight over the shared demo lots.
    """
    crops = api.data("get", "/api/crops?q=Onion")
    payload = {
        "crop_id": crops[0]["id"],
        "quantity": 50,
        "unit": "QUINTAL",
        "grade": "B",
        "expected_price": 1800,
        "district": "Nashik",
        "latitude": 20.05,
        "longitude": 73.85,
    }
    return api.data("post", "/api/lots", "farmer", json=payload, expect=201)
