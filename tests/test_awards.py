"""Night awards: pure rules, and a full run against the throwaway Postgres."""

import datetime as dt
import uuid

import pytest

import awards

UTC = dt.timezone.utc
CFG = {"min_players": 2, "min_games": 3, "duo_min_games": 5, "baseline_days": 30,
       "baseline_min_games": 10, "deadline_hour": 12}


def p(xuid, gt, team=0, kills=10, deaths=5, assists=3, score=1000):
    return {"xuid": xuid, "gamertag": gt, "team_id": team, "outcome": None, "kills": kills,
            "deaths": deaths, "assists": assists, "damage_dealt": 3000, "personal_score": score}


def game(players, outcome="win"):
    return {"players": players, "teams": [{"team_id": 0, "outcome": outcome, "score": 50},
                                          {"team_id": 1, "outcome": "loss", "score": 40}]}


# ---------- night window ----------
def test_night_of_after_midnight_is_previous_evening():
    assert awards.night_of(dt.datetime(2026, 11, 28, 7, 47, tzinfo=UTC)) == dt.date(2026, 11, 27)
    assert awards.night_of(dt.datetime(2026, 11, 28, 2, 0, tzinfo=UTC)) == dt.date(2026, 11, 27)
    assert awards.night_of(dt.datetime(2026, 11, 28, 23, 0, tzinfo=UTC)) == dt.date(2026, 11, 28)


def test_window_is_4pm_to_10am_mexico_city():
    start, end = awards.window(dt.date(2026, 11, 27))
    assert start == dt.datetime(2026, 11, 27, 22, 0, tzinfo=UTC)
    assert end == dt.datetime(2026, 11, 28, 16, 0, tzinfo=UTC)


def test_too_late_next_day_noon():
    night = dt.date(2026, 11, 27)
    assert not awards.too_late(night, dt.datetime(2026, 11, 28, 17, 39, tzinfo=UTC), 12)
    assert awards.too_late(night, dt.datetime(2026, 11, 28, 18, 0, tzinfo=UTC), 12)


# ---------- rules ----------
def test_no_group_games_no_payload():
    solo = [game([p("1", "Alpha")])]                       # only one member on the team
    assert awards.compute(solo, {}, CFG) is None


def test_mvp_is_best_score_per_game_and_needs_enough_games():
    night = [game([p("1", "Alpha", score=1500), p("2", "Bravo", score=900)]) for _ in range(6)]
    night.append(game([p("3", "Lucky", score=9000), p("2", "Bravo", score=900)]))  # one game only
    out = awards.compute(night, {}, CFG)
    assert out["games"] == 7 and out["wins"] == 7
    assert out["mvp"]["gamertag"] == "Alpha" and out["mvp"]["score_pg"] == 1500


def test_most_improved_vs_own_average_skips_mvp():
    night = [game([p("1", "Alpha", score=2000, kills=15, deaths=5),
                   p("2", "Bravo", score=800, kills=12, deaths=4)]) for _ in range(5)]
    baseline = {"1": {"games": 40, "kills": 400, "deaths": 400, "assists": 0},    # KDA 0
                "2": {"games": 40, "kills": 200, "deaths": 400, "assists": 0}}    # KDA -5
    out = awards.compute(night, baseline, CFG)
    assert out["mvp"]["gamertag"] == "Alpha"
    imp = out["improved"]
    assert imp["gamertag"] == "Bravo"                       # Alpha is MVP
    assert imp["kda_pg"] == pytest.approx(9.0) and imp["baseline_kda_pg"] == -5.0


def test_no_most_improved_when_nobody_improved_or_short_history():
    night = [game([p("1", "Alpha", kills=5, deaths=5), p("2", "Bravo")]) for _ in range(4)]
    baseline = {"1": {"games": 40, "kills": 800, "deaths": 40, "assists": 0},
                "2": {"games": 3, "kills": 0, "deaths": 30, "assists": 0}}        # too few games
    assert awards.compute(night, baseline, CFG)["improved"] is None


def test_best_duo_needs_min_games_and_half_wins():
    night = []
    for i in range(6):                                      # Alpha + Bravo: 5-1
        night.append(game([p("1", "Alpha"), p("2", "Bravo")], "win" if i else "loss"))
    for i in range(4):                                      # Alpha + Charlie: 4-0, too few
        night.append(game([p("1", "Alpha"), p("3", "Charlie")]))
    duo = awards.compute(night, {}, CFG)["duo"]
    assert duo == {"gamertags": ["Alpha", "Bravo"], "games": 6, "wins": 5, "losses": 1,
                   "win_pct": 83}
    losing = [game([p("1", "Alpha"), p("2", "Bravo")], "loss") for _ in range(6)]
    assert awards.compute(losing, {}, CFG)["duo"] is None   # nothing negative in public


def test_message_has_only_positive_lines():
    night = [game([p("1", "Alpha", score=1500), p("2", "Bravo")]) for _ in range(5)]
    text = awards.format_message(dt.date(2026, 11, 27), awards.compute(night, {}, CFG))
    assert text.startswith("🏆 Night awards (Fri Nov 27): 5 group games, 5W - 0L")
    assert "👑 MVP: Alpha" in text and "player/Alpha" in text
    assert "deaths" not in text.lower()


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("NIGHT_AWARDS", raising=False)
    assert awards.run(dt.date(2026, 11, 27)) == "off"


# ---------- full run on the database ----------
def _seed(db, night, results):
    """results: list of (outcome, [(xuid, kills, deaths, score)])"""
    db.sync_players({"101": "Alpha", "102": "Bravo", "103": "Charlie"})
    start, _ = awards.window(night)
    for n, (outcome, rows) in enumerate(results):
        when = start + dt.timedelta(hours=4, minutes=12 * n)
        mid = str(uuid.UUID(int=5000 + n))
        db.save_match({"match_id": mid, "start_time": when, "map_name": "Live Fire",
                       "mode": "Slayer", "is_ranked": False},
                      [{"match_id": mid, "team_id": 0, "outcome": outcome, "score": 50},
                       {"match_id": mid, "team_id": 1, "outcome": "loss", "score": 40}],
                      [{"match_id": mid, "xuid": x, "start_time": when, "team_id": 0,
                        "outcome": outcome, "kills": k, "deaths": d, "assists": 2,
                        "personal_score": s} for x, k, d, s in rows])


def test_run_posts_once_and_retries_after_groupme_failure(database, monkeypatch):
    monkeypatch.setenv("NIGHT_AWARDS", "1")
    night = dt.date(2026, 11, 27)
    _seed(database, night, [("win", [("101", 15, 5, 1800), ("102", 8, 6, 900)])] * 6)
    now = dt.datetime(2026, 11, 28, 7, 50, tzinfo=UTC)

    def broken(text):
        raise RuntimeError("GroupMe down")

    with pytest.raises(RuntimeError):
        awards.run(night, now=now, sender=broken)
    assert database.awards_for(night) is None                # claim released

    sent = []
    assert awards.run(night, now=now, sender=sent.append) == "posted"
    assert awards.run(night, now=now, sender=sent.append) == "already-posted"
    assert len(sent) == 1 and "👑 MVP: Alpha" in sent[0] and "Best duo: Alpha + Bravo" in sent[0]
    saved = database.awards_for(night)
    assert saved["games"] == 6 and saved["payload"]["mvp"]["gamertag"] == "Alpha"


def test_run_too_late_and_no_games(database, monkeypatch):
    monkeypatch.setenv("NIGHT_AWARDS", "1")
    night = dt.date(2026, 11, 27)
    database.sync_players({"101": "Alpha"})
    late = dt.datetime(2026, 11, 28, 19, 0, tzinfo=UTC)
    assert awards.run(night, now=late, sender=lambda t: None) == "too-late"
    early = dt.datetime(2026, 11, 28, 7, 50, tzinfo=UTC)
    assert awards.run(night, now=early, sender=lambda t: None) == "no-games"
