"""The GroupMe bot: same answers as v1.0, now answered in the background."""

import pytest

import app as bot
import sheets


@pytest.fixture
def client(monkeypatch, sent_alerts):
    posted = []

    def fake_post(url, json=None, timeout=None, **kw):
        posted.append(json)

        class R:
            status_code = 200

            def raise_for_status(self):
                pass
        return R()

    monkeypatch.setattr(bot.requests, "post", fake_post)
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    # Run background work right away so the test can check the answer
    monkeypatch.setattr(bot._executor, "submit", lambda fn, *a: fn(*a))
    monkeypatch.setattr(bot._side_executor, "submit", lambda fn, *a: None)
    monkeypatch.setattr(bot, "WEBHOOK_TOKEN", "")
    c = bot.app.test_client()
    c.posted = posted
    return c


def say(client, text, **extra):
    msg = {"text": text, "name": "Hidan", "sender_id": "123", "sender_type": "user"}
    msg.update(extra)
    return client.post("/", json=msg)


def texts(client):
    return [p.get("text") for p in client.posted]


def test_greeting_answers(client):
    r = say(client, "bot?")
    assert r.status_code == 200
    assert texts(client)[0] in ["Hello", "Mande", "Yes?", "Hola", "uh?", "Hidan?"]


def test_menu_lists_commands(client):
    say(client, "Menu!")
    assert "Available commands" in texts(client)[0]
    assert "ggs" in texts(client)[0]


def test_unknown_text_is_ignored(client):
    say(client, "just chatting about the game")
    assert client.posted == []


def test_bot_messages_are_ignored(client):
    say(client, "bot?", sender_type="bot")
    say(client, "bot?", name=bot.BOT_NAME)
    assert client.posted == []


def test_records_command_uses_sheet(client, monkeypatch):
    monkeypatch.setattr(sheets, "get_records", lambda kind: [
        {"tier": "best", "date": "", "mode": "CTF", "map": "Breaker", "result": "4:10", "link": ""}])
    say(client, "records! breaker")
    assert "MAP Breaker" in texts(client)[0]
    assert "CTF ➡️ 4:10" in texts(client)[0]


def test_sheets_failure_answers_and_alerts(client, monkeypatch, sent_alerts):
    def boom(kind):
        raise RuntimeError("quota")
    monkeypatch.setattr(sheets, "get_records", boom)
    say(client, "records! breaker")
    assert "spreadsheet brain" in texts(client)[0]
    assert sent_alerts and "cmd_records" in sent_alerts[0][0]


def test_long_messages_are_split(client):
    bot.send_message("x" * 2000)
    assert [len(t) for t in texts(client)] == [990, 990, 20]


def test_webhook_token(client, monkeypatch):
    monkeypatch.setattr(bot, "WEBHOOK_TOKEN", "s3cret")
    msg = {"text": "bot?", "name": "Hidan", "sender_type": "user"}
    assert client.post("/", json=msg).status_code == 403
    assert client.post("/?token=wrong", json=msg).status_code == 403
    assert client.post("/?token=s3cret", json=msg).status_code == 200
    assert len(client.posted) == 1


def test_handler_crash_sends_alert(client, monkeypatch, sent_alerts):
    monkeypatch.setattr(bot, "handle_message", lambda data: 1 / 0)
    r = say(client, "bot?")
    assert r.status_code == 200
    assert sent_alerts[-1][1] == "handle-message"


def test_groupme_retry(monkeypatch, sent_alerts):
    calls = []

    class R:
        def __init__(self, code):
            self.status_code = code

        def raise_for_status(self):
            pass

    codes = iter([500, 200])
    monkeypatch.setattr(bot.requests, "post", lambda *a, **k: calls.append(1) or R(next(codes)))
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    assert bot._post_to_groupme({"text": "hi"}) is True
    assert len(calls) == 2


def test_groupme_gives_up_and_alerts(monkeypatch, sent_alerts):
    class R:
        status_code = 503

        def raise_for_status(self):
            pass
    monkeypatch.setattr(bot.requests, "post", lambda *a, **k: R())
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    assert bot._post_to_groupme({"text": "hi"}) is False
    assert sent_alerts[-1][1] == "groupme-post"


def test_health_light(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] in ("ok", "degraded")
    assert "sheets" not in body["checks"]


def test_health_deep_reports_sheets(client, monkeypatch):
    monkeypatch.setattr(bot, "GROUPME_BOT_ID", "abc")
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(1)
    monkeypatch.setattr(bot, "_side_executor", pool)
    monkeypatch.setattr(sheets, "_values", lambda name, **kw: [["x"]])
    body = client.get("/health?deep=1").get_json()
    assert body["checks"]["sheets"] == "ok"
    assert body["status"] == "ok"

    def broken(name, **kw):
        raise RuntimeError("no access")
    monkeypatch.setattr(sheets, "_values", broken)
    body = client.get("/health?deep=1").get_json()
    assert body["checks"]["sheets"].startswith("error")
    assert body["status"] == "degraded"
