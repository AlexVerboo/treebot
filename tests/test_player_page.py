"""Player page: rate math, strong/weak maps, duos, the SQL and the Flask routes."""

import datetime as dt
import uuid

import pytest

import app as bot
import player_page

UTC = dt.timezone.utc
CFG = {"trend_days": 30, "window_days": 90, "duo_min_games": 5, "map_min_games": 3}


def sums(games, wins, kills=0, deaths=0, assists=0, **extra):
    return {"games": games, "wins": wins, "kills": kills, "deaths": deaths, "assists": assists,
            **extra}


# ---------- pure ----------
def test_rates_zero_games_is_all_none():
    r = player_page.rates(sums(0, 0))
    assert r["games"] == 0 and r["kd"] is None and r["win_pct"] is None


def test_rates_math():
    r = player_page.rates(sums(4, 3, kills=40, deaths=20, assists=12, damage_dealt=16000,
                               shots_hit=50, shots_fired=200))
    assert r["win_pct"] == 75.0 and r["kd"] == 2.0 and r["kda_pg"] == 6.0
    assert r["dmg_pg"] == 4000 and r["accuracy"] == 25.0 and r["losses"] == 1


def test_strong_and_weak_maps_do_not_overlap():
    rows = [{"map": "A", **sums(10, 8)}, {"map": "B", **sums(10, 6)}, {"map": "C", **sums(10, 5)},
            {"map": "D", **sums(10, 2)}, {"map": "E", **sums(2, 0)}]   # E: too few games
    full, strong, weak = player_page.strong_weak(rows, "map", 3)
    assert [r["map"] for r in strong] == ["A", "B", "C"]
    assert [r["map"] for r in weak] == ["D"]
    assert len(full) == 5


def test_no_weak_list_with_few_maps():
    rows = [{"map": "A", **sums(5, 1)}, {"map": "B", **sums(5, 0)}]
    _, strong, weak = player_page.strong_weak(rows, "map", 3)
    assert len(strong) == 2 and weak == []


def test_duos_filter_and_order():
    rows = [{"gamertag": "X", "active": True, **sums(8, 6)},
            {"gamertag": "Y", "active": True, **sums(4, 4)},
            {"gamertag": "Z", "active": True, **sums(10, 9)}]
    assert [d["gamertag"] for d in player_page.duos(rows, 5)] == ["Z", "X"]


# ---------- with the database ----------
def _seed(db, now):
    db.sync_players({"101": "Alpha One", "102": "Bravo", "103": "Charlie"})
    for n in range(8):
        when = now - dt.timedelta(days=n % 4, hours=2)
        mid = str(uuid.UUID(int=7000 + n))
        outcome = "win" if n < 6 else "loss"
        db.save_match(
            {"match_id": mid, "start_time": when, "map_name": "Live Fire" if n % 2 else "Recharge",
             "mode": "Slayer", "is_ranked": False},
            [{"match_id": mid, "team_id": 0, "outcome": outcome, "score": 50},
             {"match_id": mid, "team_id": 1, "outcome": "loss" if outcome == "win" else "win",
              "score": 45}],
            [{"match_id": mid, "xuid": "101", "start_time": when, "team_id": 0, "outcome": outcome,
              "kills": 12, "deaths": 6, "assists": 3, "damage_dealt": 4000, "shots_hit": 40,
              "shots_fired": 100, "personal_score": 1500},
             {"match_id": mid, "xuid": "102", "start_time": when, "team_id": 0, "outcome": outcome,
              "kills": 6, "deaths": 6, "assists": 6, "damage_dealt": 3000, "personal_score": 900}])


def test_load_player_from_database(database):
    now = dt.datetime.now(UTC)
    _seed(database, now)
    player_page.clear_cache()
    data = player_page.load("alphaone", roles_for=lambda gt: ["Roamer"],
                            profile_for=lambda gt: "https://example.test/p")
    assert data["gamertag"] == "Alpha One" and data["roles"] == ["Roamer"]
    s = data["trend_summary"]
    assert s["games"] == 8 and s["wins"] == 6 and s["kd"] == 2.0 and s["accuracy"] == 40.0
    assert data["group"]["games"] == 16
    assert sum(d["games"] for d in data["trend"]) == 8
    assert {m["map"] for m in data["maps"]} == {"Live Fire", "Recharge"}
    assert data["duos"][0]["gamertag"] == "Bravo" and data["duos"][0]["games"] == 8
    assert len(data["recent"]) == 8 and data["recent"][0]["score"] in ("50-45", "45-50")
    with pytest.raises(player_page.NotFound):
        player_page.load("nobody")


def test_sheets_failure_does_not_break_the_page(database):
    _seed(database, dt.datetime.now(UTC))
    player_page.clear_cache()

    def boom(gt):
        raise RuntimeError("Sheets down")
    data = player_page.load("Bravo", roles_for=boom, profile_for=boom)
    assert data["roles"] == [] and data["trend_summary"]["games"] == 8


# ---------- routes ----------
@pytest.fixture
def web(monkeypatch, sent_alerts):
    monkeypatch.setattr(bot._side_executor, "submit", lambda fn, *a: None)
    player_page.clear_cache()
    return bot.app.test_client()


def test_routes_without_database_are_503(web, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert web.get("/player/Alpha").status_code == 503
    assert web.get("/api/player/Alpha").status_code == 503


def test_routes_with_database(web, database, monkeypatch):
    _seed(database, dt.datetime.now(UTC))
    monkeypatch.setattr(bot, "_roles_for", lambda gt: [])
    monkeypatch.setattr(bot, "_profile_for", lambda gt: "")
    r = web.get("/player/Alpha%20One")
    assert r.status_code == 200 and b"Alpha One" in r.data
    j = web.get("/api/player/alpha one").get_json()
    assert j["trend_summary"]["games"] == 8
    r = web.get("/player/Ghost")
    assert r.status_code == 404 and b"know that Tree" in r.data
