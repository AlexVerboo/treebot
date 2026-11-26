import asyncio
import base64
import types

import pytest

import halo_auth


def test_save_without_token_alerts(monkeypatch, sent_alerts):
    monkeypatch.delenv("GH_SECRETS_TOKEN", raising=False)
    assert halo_auth.save_refresh_token("new") is False
    assert sent_alerts[0][1] == "halo-token-not-saved"


def test_save_encrypts_and_puts(monkeypatch, sent_alerts, fake_response):
    from nacl import public
    private = public.PrivateKey.generate()
    pub = base64.b64encode(bytes(private.public_key)).decode()
    calls = {}

    def get(url, **kw):
        calls["get"] = url
        return fake_response(200, {"key": pub, "key_id": "k1"})

    def put(url, json=None, **kw):
        calls["put"] = (url, json)
        return fake_response(204)

    monkeypatch.setenv("GH_SECRETS_TOKEN", "ghp_test")
    monkeypatch.setattr(halo_auth.requests, "get", get)
    monkeypatch.setattr(halo_auth.requests, "put", put)
    assert halo_auth.save_refresh_token("brand-new-token") is True
    url, body = calls["put"]
    assert url.endswith("/actions/secrets/HALO_REFRESH_TOKEN")
    assert body["key_id"] == "k1"
    clear = public.SealedBox(private).decrypt(base64.b64decode(body["encrypted_value"]))
    assert clear == b"brand-new-token"
    assert sent_alerts == []


def test_save_failure_alerts(monkeypatch, sent_alerts, fake_response):
    monkeypatch.setenv("GH_SECRETS_TOKEN", "ghp_test")
    monkeypatch.setattr(halo_auth.requests, "get", lambda url, **kw: fake_response(403))
    assert halo_auth.save_refresh_token("x") is False
    assert sent_alerts[0][1] == "halo-token-not-saved"


def _fake_spnkr(monkeypatch, new_refresh="rt-new", fail=False):
    from spnkr.auth import halo, oauth, xbox

    async def refresh(session, token, app):
        if fail:
            raise RuntimeError("invalid_grant")
        return types.SimpleNamespace(access_token="at", raw={"refresh_token": new_refresh})

    async def user_token(session, at):
        return types.SimpleNamespace(token="ut")

    async def xsts(session, ut, audience):
        return types.SimpleNamespace(token="xt", xuid="123", gamertag="Hidan Mx",
                                     authorization_header_value="XBL3.0 x")

    async def spartan(session, t):
        return types.SimpleNamespace(token="st")

    async def clearance(session, t):
        return types.SimpleNamespace(token="ct")

    monkeypatch.setattr(oauth, "refresh_oauth_token", refresh)
    monkeypatch.setattr(xbox, "request_user_token", user_token)
    monkeypatch.setattr(xbox, "request_xsts_token", xsts)
    monkeypatch.setattr(halo, "request_spartan_token", spartan)
    monkeypatch.setattr(halo, "request_clearance_token", clearance)


def test_login_keeps_new_token(monkeypatch, tmp_path, sent_alerts):
    _fake_spnkr(monkeypatch)
    saved = []
    monkeypatch.setattr(halo_auth, "save_refresh_token", lambda t: saved.append(t) or True)
    env_file = tmp_path / "env"
    monkeypatch.setenv("GITHUB_ENV", str(env_file))
    monkeypatch.setenv("HALO_REFRESH_TOKEN", "rt-old")
    monkeypatch.delenv("HALO_REFRESH_TOKEN_NEW", raising=False)
    from spnkr import AzureApp
    player = asyncio.run(halo_auth.login(None, AzureApp("id", "secret", "https://localhost")))
    assert player.gamertag == "Hidan Mx"
    assert player.spartan_token.token == "st"
    assert saved == ["rt-new"]
    assert "HALO_REFRESH_TOKEN_NEW=rt-new" in env_file.read_text()


def test_login_failure_alerts_and_raises(monkeypatch, sent_alerts):
    _fake_spnkr(monkeypatch, fail=True)
    monkeypatch.setenv("HALO_REFRESH_TOKEN", "rt-old")
    monkeypatch.delenv("HALO_REFRESH_TOKEN_NEW", raising=False)
    from spnkr import AzureApp
    with pytest.raises(RuntimeError):
        asyncio.run(halo_auth.login(None, AzureApp("id", "secret", "https://localhost")))
    assert sent_alerts[0][1] == "halo-login"
    assert "get_halo_token.py" in sent_alerts[0][0]
