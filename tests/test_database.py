"""Database layer, migrations and ingestion against a throwaway local Postgres."""

import asyncio
import datetime as dt
import os

import pytest

import ingest
import migrate
from fakes import T0, FakeHalo, match, mid

A, B, C = "2533274800000001", "2533274800000002", "2533274800000003"


def run(coro):
    return asyncio.run(coro)


# ---------- pure helpers (no database) ----------
def test_plan_fetch_skips_complete_matches():
    seen = {"m1": {A}, "m2": {A, B}, "m3": {B}}
    existing = {("m1", A), ("m2", A)}
    assert sorted(ingest.plan_fetch(seen, existing)) == ["m2", "m3"]


def test_rows_keep_only_members():
    m = match(1, players=[(A, 0, "win", 12), ("999", 1, "loss", 3)])
    rows = ingest.player_rows(m, {A: "Alpha"})
    assert [r["xuid"] for r in rows] == [A]
    assert rows[0]["kills"] == 12 and rows[0]["medals"] == {"1512363953": 2}
    info = ingest.match_row(m, "Live Fire - Ranked", "Ranked Arena")
    assert info["is_ranked"] and info["map_name"] == "Live Fire" and info["mode"] == "Slayer"
    assert info["duration_s"] == 600


def test_conninfo_forces_ssl(monkeypatch):
    import db
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-x-pooler.neon.tech/neondb")
    assert "sslmode=require" in db.conninfo()
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-x.neon.tech/neondb?sslmode=verify-full")
    assert "sslmode=verify-full" in db.conninfo()
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/x")
    assert "sslmode" not in db.conninfo()


def test_disabled_without_url(monkeypatch):
    import db
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert not db.enabled()
    with pytest.raises(db.DatabaseDisabled):
        db.conninfo()


# ---------- migrations ----------
def test_migrate_is_idempotent(database):
    with database.connect_direct() as conn:
        assert migrate.apply(conn) == []          # the fixture already applied everything
        assert dict(migrate.status(conn))["001_initial"] == "applied"


def test_migrate_refuses_edited_migration(database, tmp_path):
    (tmp_path / "001_initial.sql").write_text("SELECT 1;")
    with database.connect_direct() as conn, pytest.raises(migrate.MigrationError):
        migrate.apply(conn, directory=str(tmp_path))


def test_new_migration_is_applied_once(database, tmp_path):
    import shutil
    shutil.copy(os.path.join(migrate.MIGRATIONS_DIR, "001_initial.sql"), tmp_path)
    (tmp_path / "002_extra.sql").write_text("CREATE TABLE extra (id int);")
    with database.connect_direct() as conn:
        assert migrate.apply(conn, directory=str(tmp_path)) == ["002_extra"]
        assert migrate.apply(conn, directory=str(tmp_path)) == []


# ---------- players ----------
def test_sync_players_new_renamed_and_gone(database):
    assert sorted(database.sync_players({A: "Alpha", B: "Bravo"})) == [A, B]
    assert database.sync_players({A: "Alpha2", B: "Bravo"}) == []          # rename only
    assert database.sync_players({A: "Alpha2"}) == []                      # B leaves
    assert database.sync_players({A: "Alpha2", B: "Bravo"}) == [B]         # B comes back
    assert database.sync_players({}) == []                                 # Sheets failure: no-op
    with database.connection() as conn:
        rows = dict(conn.execute("SELECT gamertag, active FROM players").fetchall())
    assert rows == {"Alpha2": True, "Bravo": True}


# ---------- ingestion ----------
def test_second_ingest_asks_halo_nothing(database):
    m1 = match(1, T0, [(A, 0, "win", 10), (B, 0, "win", 8)])
    m2 = match(2, T0 + dt.timedelta(hours=1), [(A, 1, "loss", 4)])
    halo = FakeHalo({A: [m2, m1], B: [m1]})
    members = {A: "Alpha", B: "Bravo"}
    first = run(ingest.run(halo, members, days=3650))
    assert first["new_matches"] == 2 and first["new_rows"] == 3
    assert sorted(halo.stats_calls) == [mid(1), mid(2)]

    halo.stats_calls.clear()
    second = run(ingest.run(halo, members, days=3650))
    assert halo.stats_calls == []                 # never ask Halo for a stored match
    assert second["new_matches"] == 0 and second["new_rows"] == 0


def test_new_member_gets_backfilled(database):
    shared = match(1, T0, [(A, 0, "win", 10), (C, 0, "win", 7)])
    halo = FakeHalo({A: [shared], C: [shared]})
    run(ingest.run(halo, {A: "Alpha"}, days=3650))          # C is not a member yet
    with database.connection() as conn:
        assert conn.execute("SELECT count(*) FROM match_players").fetchone()[0] == 1

    halo.stats_calls.clear()
    res = run(ingest.run(halo, {A: "Alpha", C: "Charlie"}, only="Charlie", days=3650))
    assert halo.stats_calls == [mid(1)]           # fetched once more, only for C's row
    assert res["new_matches"] == 0 and res["new_rows"] == 1
    with database.connection() as conn:
        assert conn.execute("SELECT count(*) FROM match_players").fetchone()[0] == 2


def test_ingest_run_is_logged(database):
    halo = FakeHalo({A: [match(1, T0, [(A, 0, "win", 1)])]})
    run(ingest.run(halo, {A: "Alpha"}, source="night", days=3650))
    info = database.health()
    assert info["status"] == "ok"
    assert info["last_ingest"]["source"] == "night"
    assert info["last_ingest"]["status"] == "ok"
    assert info["last_ingest"]["new_matches"] == 1


# ---------- ggs from the database ----------
def test_ggs_summary_from_db(database, monkeypatch):
    import ggs_summary
    monkeypatch.setattr(ggs_summary, "MIN_PLAYERS", 2)
    together = match(1, T0, [(A, 0, "win", 10), (B, 0, "win", 6)])
    solo = match(2, T0 + dt.timedelta(minutes=20), [(A, 0, "loss", 3)])
    halo = FakeHalo({A: [solo, together], B: [together]})
    members = {A: "Alpha", B: "Bravo"}
    run(ingest.run(halo, members, days=3650))
    games, totals = ggs_summary.summary_from_db(
        database.matches_since(T0 - dt.timedelta(hours=1), list(members)))
    assert games == [{"ranked": False, "win": True, "tie": False, "map": "Live Fire",
                      "mode": "Slayer", "score": "50-43"}]
    assert totals["Alpha"]["kills"] == 10 and totals["Bravo"]["games"] == 1
    assert "1W - 0L" in ggs_summary.format_summary(games, totals)


def test_ggs_falls_back_to_halo_when_db_fails(monkeypatch, sent_alerts):
    import ggs_summary
    import ingest as ingest_mod

    async def broken(*a, **kw):
        raise ConnectionError("neon down")

    async def from_halo(client, members, since):
        return ["halo"], {}

    monkeypatch.setattr(ingest_mod, "run", broken)
    monkeypatch.setattr(ggs_summary, "build_summary", from_halo)
    games, _ = run(ggs_summary.summary_with_db(None, {}, T0))
    assert games == ["halo"]
    assert sent_alerts and sent_alerts[-1][1] == "db-ggs"


# ---------- snapshots and the Sheets import ----------
def test_snapshots_upsert_and_import_keeps_existing(database):
    database.sync_players({A: "Alpha"})
    day = dt.date(2026, 11, 26)
    assert database.save_snapshots([{"xuid": A, "snapshot_date": day, "matches": 10,
                                     "row": {"matches": 10}}]) == 1
    database.save_snapshots([{"xuid": A, "snapshot_date": day, "matches": 11,
                              "row": {"matches": 11}}])                     # same day: update
    database.save_snapshots([{"xuid": A, "snapshot_date": day, "matches": 1, "row": {}}],
                            overwrite=False)                                # import: keep
    with database.connection() as conn:
        assert conn.execute("SELECT matches, row FROM stats_snapshots").fetchall() == \
            [(11, {"matches": 11})]


def test_parse_sheets_for_import():
    import import_sheets
    players = import_sheets.parse_players(
        [["gamertag", "xuid"], ["Alpha", A], ["Old Guy", B], ["bad", "x"], ["Alpha", A]],
        ["alpha"])
    assert players == [(int(A), "Alpha", True), (int(B), "Old Guy", False)]
    rows, date = import_sheets.parse_stats(
        [["gamertag", "matches", "kd"], ["Alpha", 120, "1,25"], ["updated", "2026-11-26 03:10 UTC"]])
    assert rows == {"Alpha": {"matches": 120, "kd": 1.25}}
    assert date == dt.date(2026, 11, 25)                 # 03:10 UTC is still the 25th in CDMX
    snaps, missing = import_sheets.snapshots_from_sheet({**rows, "Ghost": {}}, date, players)
    assert snaps[0]["xuid"] == int(A) and snaps[0]["matches"] == 120 and missing == ["Ghost"]


def test_health_deep_reports_database(monkeypatch):
    import app as bot
    import db
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(bot, "_side_executor", ThreadPoolExecutor(2))
    monkeypatch.setattr(bot.sheets, "_values", lambda name, **kw: [["x"]])
    monkeypatch.setattr(bot.scheduler, "maybe_run", lambda: None)
    client = bot.app.test_client()

    assert client.get("/health?deep=1").get_json()["checks"]["database"] == "off"

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example/x")
    monkeypatch.setattr(db, "health", lambda timeout: {"status": "ok", "last_ingest": None})
    body = client.get("/health?deep=1").get_json()
    assert body["checks"]["database"] == "ok" and body["status"] in ("ok", "degraded")

    def down(timeout):
        raise OSError("no route")
    monkeypatch.setattr(db, "health", down)
    r = client.get("/health?deep=1")
    assert r.status_code == 200
    body = r.get_json()
    assert body["checks"]["database"] == "error: OSError" and body["status"] == "degraded"


def _service_record():
    from spnkr.models.stats import ServiceRecord, ServiceRecordCoreStats
    from types import SimpleNamespace as NS
    c = ServiceRecordCoreStats.model_construct(
        kills=500, deaths=400, assists=200, damage_dealt=90000, damage_taken=80000,
        accuracy=51.234, medals=(NS(name_id=1, count=2),), personal_scores=())
    return ServiceRecord.model_construct(
        matches_completed=100, wins=55, losses=44, ties=1,
        time_played=dt.timedelta(hours=20), core_stats=c, subqueries=None)


def test_stats_snapshot_from_service_record(database):
    import player_stats_updater as psu
    database.sync_players({A: "Alpha"})
    snap = psu.snapshot(A, {"matches": 100}, _service_record(), dt.date(2026, 11, 26))
    assert snap["kills"] == 500 and snap["accuracy"] == 51.23 and snap["time_played_s"] == 72000
    assert "medals" not in snap["record"]["core_stats"]
    assert database.save_snapshots([snap]) == 1


def test_snapshots_db_failure_only_alerts(monkeypatch, sent_alerts):
    import db
    import player_stats_updater as psu
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example/x")
    monkeypatch.setattr(psu, "DRY_RUN", False)

    def down(members):
        raise OSError("neon down")
    monkeypatch.setattr(db, "sync_players", down)
    psu.save_snapshots({A: "Alpha"}, {"Alpha": {}}, {"Alpha": _service_record()})  # no raise
    assert sent_alerts[-1][1] == "db-snapshots"
