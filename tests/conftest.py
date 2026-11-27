import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Tests never touch real services
for var in ("DISCORD_ALERT_WEBHOOK", "GH_DISPATCH_TOKEN", "GH_SECRETS_TOKEN",
            "WEBHOOK_TOKEN", "GOOGLE_CREDENTIALS_JSON", "GITHUB_ENV", "DATABASE_URL"):
    os.environ.pop(var, None)


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        import requests
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def fake_response():
    return FakeResponse


@pytest.fixture
def sent_alerts(monkeypatch):
    import alerts
    calls = []
    monkeypatch.setattr(alerts, "send", lambda text, key=None, source=None: calls.append((text, key)) or True)
    return calls


# ==============================
# Database tests: a throwaway Postgres in TEST_DATABASE_URL (CI starts one).
# Without it these tests are skipped. Never point it at Neon: every test wipes the schema.
# ==============================
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")


@pytest.fixture
def database(monkeypatch):
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    if "neon.tech" in TEST_DATABASE_URL:
        pytest.exit("TEST_DATABASE_URL must be a throwaway local database, not Neon")
    import psycopg
    import db
    import migrate
    db.close()
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        migrate.apply(conn)
    yield db
    db.close()
