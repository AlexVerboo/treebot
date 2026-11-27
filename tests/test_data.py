"""Pure data helpers: sheet parsing, records comparison, player stats, snakemagic, alerts."""

import player_stats_updater as psu
import records_updater as ru
import sheets
import snakemagic
import alerts


# ---------- sheets.py ----------
def test_clean_result():
    assert sheets._clean_result("2:32:00") == "2:32"
    assert sheets._clean_result("3:19:") == "3:19"
    assert sheets._clean_result("---") == ""


def test_clean_date_serial():
    assert sheets._clean_date("44941") == "15/01/2023"
    assert sheets._clean_date("---") == ""


def test_parse_records_two_blocks():
    rows = [
        ["Date", "Mode", "Map", "Time", "Image", "Link", "Date", "Mode", "Map", "Time", "Image", "Link"],
        ["01/01/2026", "CTF", "Breaker", "4:10", "", "https://x", "02/01/2026", "CTF", "Breaker", "4:30", "", ""],
        ["", "", "", "", "", ""],
    ]
    out = sheets._parse_records(rows)
    assert [(r["tier"], r["result"]) for r in out] == [("best", "4:10"), ("good", "4:30")]
    assert out[0]["link"] == "https://x"


def test_player_stats_decimal_comma(monkeypatch):
    monkeypatch.setattr(sheets, "_optional_values", lambda name, raw=False: [
        ["gamertag", "kd", "matches"], ["Hidan Mx", "1,25", 300], ["updated", "2026-11-26"]])
    stats, updated = sheets.get_player_stats()
    assert stats["Hidan Mx"] == {"kd": 1.25, "matches": 300.0}
    assert updated == "2026-11-26"


# ---------- records_updater.py ----------
def test_parse_result():
    assert ru.parse_result("CTF", "2:32") == -152
    assert ru.parse_result("CTF", "24m 17s") == -(24 * 60 + 17)
    assert ru.parse_result("One Flag", "3-0 / 11:48") == -(11 * 60 + 48)
    assert ru.parse_result("Slayer", "100-62") == 38
    assert ru.parse_result("CTF", "---") is None


def test_record_result_formats():
    import datetime as dt
    d = dt.timedelta(minutes=11, seconds=48)
    assert ru.record_result("One Flag", 3, 0, d) == ("3-0 / 11:48", -708)
    assert ru.record_result("Slayer", 100, 62, d) == ("100-62", 38)
    assert ru.record_result("Capture the Flag", 3, 1, d) == ("11:48", -708)
    # an old One Flag record ("11:48") and a new one compare by time
    assert ru.parse_result("One Flag", "11:48") == ru.record_result("One Flag", 3, 0, d)[1]


def test_kind_for_playlist():
    assert ru.kind_for_playlist("Big Team Battle") == "btb"
    assert ru.kind_for_playlist("Squad Battle") == "squad"
    assert ru.kind_for_playlist("Heavies") == "heavies"
    assert ru.kind_for_playlist("Quick Play") is None


# ---------- player_stats_updater.py ----------
def test_merge_keeps_yesterday_for_failed_members():
    today = {"Hidan Mx": {"matches": 10}}
    previous = {"Verlock": {"matches": "7"}, "Gone Player": {"matches": "3"}}
    merged, kept = psu.merge_with_previous(today, previous, ["Hidan Mx", "Verlock"])
    assert kept == ["Verlock"]
    assert "Gone Player" not in merged
    assert merged["Hidan Mx"] == {"matches": 10}


class FakeWS:
    def __init__(self, rows=40):
        self.row_count = rows
        self.calls = []

    def update(self, **kw):
        self.calls.append(("update", len(kw["values"])))

    def batch_clear(self, ranges):
        self.calls.append(("batch_clear", ranges))

    def add_rows(self, n):
        self.row_count += n

    def clear(self):
        self.calls.append(("clear",))


def test_write_stats_never_clears_first(monkeypatch):
    ws = FakeWS(rows=40)
    monkeypatch.setattr(psu, "DRY_RUN", False)
    monkeypatch.setattr(psu, "previous_rows", lambda book: {})
    monkeypatch.setattr(psu, "_worksheet", lambda book, name, r, c: (ws, False))
    psu.write_stats(object(), {"A": {"matches": 1}, "B": {"matches": 2}}, ["A", "B"])
    assert ws.calls[0][0] == "update"            # data first
    assert ("clear",) not in ws.calls            # never wipes the whole sheet
    assert ws.calls[1] == ("batch_clear", ["A5:ZZ40"])  # header + 2 players + "updated" = 4 rows


def test_write_stats_with_nobody_keeps_sheet(monkeypatch):
    ws = FakeWS()
    monkeypatch.setattr(psu, "DRY_RUN", False)
    monkeypatch.setattr(psu, "previous_rows", lambda book: {})
    monkeypatch.setattr(psu, "_worksheet", lambda book, name, r, c: (ws, False))
    psu.write_stats(object(), {}, [])
    assert ws.calls == []


# ---------- snakemagic.py ----------
def test_parse_videos():
    html = ("feat=[['Snake Intro','desc','img.jpg','yt','abcdefghijk','1:23']];\n"
            "const all=`abcdefghijk|Snake Intro|1:23\nzyxwvutsrqp|Turret Time|0:45`;")
    videos = snakemagic.parse_videos(html)
    assert [v["title"] for v in videos] == ["Snake Intro", "Turret Time"]
    assert videos[1]["dur"] == "0:45"


# ---------- alerts.py ----------
def test_alerts_without_webhook_do_nothing(monkeypatch):
    monkeypatch.delenv("DISCORD_ALERT_WEBHOOK", raising=False)
    assert alerts.send("hi") is False


def test_alerts_rate_limit(monkeypatch):
    sent = []

    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setenv("DISCORD_ALERT_WEBHOOK", "https://discord.test/webhook")
    monkeypatch.setattr(alerts.urllib.request, "urlopen", lambda req, timeout: sent.append(req) or R())
    alerts._last_sent.clear()
    assert alerts.send("first", key="k") is True
    assert alerts.send("again", key="k") is False   # same key within MIN_INTERVAL
    assert alerts.send("other", key="z") is True
    assert len(sent) == 2
