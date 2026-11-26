import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Tests never touch real services
for var in ("DISCORD_ALERT_WEBHOOK", "GH_DISPATCH_TOKEN", "GH_SECRETS_TOKEN",
            "WEBHOOK_TOKEN", "GOOGLE_CREDENTIALS_JSON", "GITHUB_ENV"):
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
