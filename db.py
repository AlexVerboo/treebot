"""
Postgres (Neon) access for TreeBot v2.0. All SQL lives here.

- DATABASE_URL turns the database on. Without it every caller skips the DB and the bot
  works exactly as in v1 (Sheets only). In GitHub Actions the secret is NEON_PROD_POOLER,
  mapped to DATABASE_URL in the workflows; on Render the variable is DATABASE_URL.
- Use Neon's *pooled* connection string (host with "-pooler"). The pooler is PgBouncer in
  transaction mode, which does not support prepared statements, so they are turned off
  (prepare_threshold=None).
- sslmode=require is forced for any host that is not local.
- The pool keeps no idle connections (min_size=0, max_idle=60 s), so Neon can suspend its
  compute when nobody is using it (the free plan counts compute hours).

psycopg is imported lazily: importing this module never fails, even if the package is missing.
"""

import datetime as dt
import os
import threading
import uuid
from contextlib import contextmanager

CDMX = dt.timezone(dt.timedelta(hours=-6))   # Mexico City has no DST since 2022
CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))
POOL_MAX = int(os.getenv("DB_POOL_MAX", "4"))

_pool = None
_pool_lock = threading.Lock()


class DatabaseDisabled(RuntimeError):
    """DATABASE_URL is not set."""


def url():
    return (os.getenv("DATABASE_URL") or "").strip()


def enabled():
    return bool(url())


def conninfo(raw=None):
    """Connection string with sslmode=require added when it is missing (non-local hosts)."""
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    raw = raw if raw is not None else url()
    if not raw:
        raise DatabaseDisabled("DATABASE_URL is not set")
    params = conninfo_to_dict(raw)
    host = str(params.get("host") or "")
    local = host in ("", "localhost", "127.0.0.1", "::1") or host.startswith("/")
    if not local and "sslmode" not in params:
        params["sslmode"] = "require"
    return make_conninfo(**params)


def _connect_kwargs():
    return {"prepare_threshold": None, "connect_timeout": CONNECT_TIMEOUT,
            "application_name": os.getenv("DB_APP_NAME", "treebot")}


def get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            from psycopg_pool import ConnectionPool
            _pool = ConnectionPool(conninfo(), min_size=0, max_size=POOL_MAX, max_idle=60,
                                   timeout=CONNECT_TIMEOUT + 5, kwargs=_connect_kwargs(),
                                   name="treebot", open=True)
        return _pool


def close():
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


@contextmanager
def connection(timeout=None):
    """A pooled connection. Commits on success, rolls back on error."""
    with get_pool().connection(timeout=timeout) as conn:
        yield conn


def connect_direct(timeout=None):
    """One connection outside the pool (migrations, health checks)."""
    import psycopg
    kwargs = _connect_kwargs()
    if timeout:
        kwargs["connect_timeout"] = max(1, int(timeout))
    return psycopg.connect(conninfo(), **kwargs)


def _jsonb(value):
    from psycopg.types.json import Jsonb
    return None if value is None else Jsonb(value)


def _uuid(value):
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


# ==============================
# Health
# ==============================
def health(timeout=3):
    """{"status": "ok", "last_ingest": {...} | None}. Raises if the DB does not answer."""
    with connect_direct(timeout=timeout) as conn:
        conn.execute(f"SET statement_timeout = {int(timeout * 1000)}")
        conn.execute("SELECT 1")
        last = None
        try:
            row = conn.execute(
                "SELECT source, started_at, finished_at, new_matches, status "
                "FROM ingest_runs ORDER BY id DESC LIMIT 1").fetchone()
        except Exception:      # tables not created yet (migrate.py not run)
            row = None
        if row:
            last = {"source": row[0], "started_at": row[1].isoformat(),
                    "finished_at": row[2].isoformat() if row[2] else None,
                    "new_matches": row[3], "status": row[4]}
        return {"status": "ok", "last_ingest": last}


# ==============================
# Players
# ==============================
def sync_players(members):
    """Mirror the Sheets members list. members: {xuid (str|int): gamertag}.
    Inserts new members, renames, reactivates, and marks missing ones inactive.
    Returns the xuids (str) that are new or came back: they need a longer backfill."""
    if not members:          # empty list = Sheets problem, never deactivate everyone
        return []
    wanted = {int(x): gt for x, gt in members.items()}
    with connection() as conn, conn.transaction():
        before = dict(conn.execute("SELECT xuid, active FROM players").fetchall())
        # 1) free the gamertags of people who left (unique index on active gamertags)
        conn.execute("UPDATE players SET active = false, updated_at = now() "
                     "WHERE active AND NOT (xuid = ANY(%s))", (list(wanted),))
        # 2) add new members, rename and reactivate (rows that did not change are not touched)
        for xuid, gt in wanted.items():
            conn.execute(
                "INSERT INTO players (xuid, gamertag) VALUES (%s, %s) "
                "ON CONFLICT (xuid) DO UPDATE SET gamertag = EXCLUDED.gamertag, active = true, "
                "updated_at = now() "
                "WHERE players.gamertag IS DISTINCT FROM EXCLUDED.gamertag OR NOT players.active",
                (xuid, gt))
    return [str(x) for x in wanted if before.get(x) is not True]


def import_players(rows):
    """One-time import: rows = [(xuid, gamertag, active)]. Existing rows are left alone."""
    with connection() as conn, conn.transaction():
        n = 0
        for xuid, gt, active in rows:
            cur = conn.execute("INSERT INTO players (xuid, gamertag, active) VALUES (%s, %s, %s) "
                               "ON CONFLICT DO NOTHING", (int(xuid), gt, active))
            n += cur.rowcount
        return n


# ==============================
# Matches
# ==============================
def existing_rows(match_ids):
    """{(match_id str, xuid str)} already stored, among the given match ids."""
    ids = [_uuid(m) for m in match_ids]
    if not ids:
        return set()
    with connection() as conn:
        rows = conn.execute("SELECT match_id, xuid FROM match_players WHERE match_id = ANY(%s)",
                            (ids,)).fetchall()
    return {(str(m), str(x)) for m, x in rows}


MATCH_COLS = ("match_id", "start_time", "end_time", "duration_s", "map_asset_id",
              "map_version_id", "map_name", "mode", "mode_category", "playlist_id",
              "playlist_name", "lifecycle", "is_ranked", "season_id")
TEAM_COLS = ("match_id", "team_id", "outcome", "rank", "score")
PLAYER_COLS = ("match_id", "xuid", "start_time", "team_id", "outcome", "rank", "kills",
               "deaths", "assists", "damage_dealt", "damage_taken", "shots_fired", "shots_hit",
               "accuracy", "score", "personal_score", "headshot_kills", "melee_kills",
               "grenade_kills", "power_weapon_kills", "callout_assists", "max_killing_spree",
               "driver_assists", "vehicle_destroys", "hijacks", "time_played_s",
               "joined_in_progress", "present_at_completion", "mode_stats", "medals")
UUID_COLS = {"match_id", "map_asset_id", "map_version_id", "playlist_id"}
JSON_COLS = {"mode_stats", "medals"}


def _values(cols, row):
    out = []
    for c in cols:
        v = row.get(c)
        if c in UUID_COLS:
            v = _uuid(v)
        elif c in JSON_COLS:
            v = _jsonb(v)
        elif c == "xuid":
            v = int(v)
        out.append(v)
    return out


def _insert_sql(table, cols):
    return (f"INSERT INTO {table} ({', '.join(cols)}) "
            f"VALUES ({', '.join(['%s'] * len(cols))}) ON CONFLICT DO NOTHING")


def save_match(match, teams, players):
    """Stores one match atomically (all or nothing). Already stored rows are skipped
    (ON CONFLICT DO NOTHING), so calling it twice is harmless.
    Returns (match_was_new, player_rows_added)."""
    with connection() as conn, conn.transaction():
        new = conn.execute(_insert_sql("matches", MATCH_COLS),
                           _values(MATCH_COLS, match)).rowcount == 1
        for t in teams:
            conn.execute(_insert_sql("match_teams", TEAM_COLS), _values(TEAM_COLS, t))
        added = 0
        for p in players:
            added += conn.execute(_insert_sql("match_players", PLAYER_COLS),
                                  _values(PLAYER_COLS, p)).rowcount
    return new, added


def matches_since(since, xuids, until=None):
    """Matches in [since, until) with the given members' rows, oldest first.
    [{match_id, start_time, map, mode, ranked, teams: [...], players: [...]}]"""
    ids = [int(x) for x in xuids]
    until = until or dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
    sql = """
        SELECT m.match_id, m.start_time, m.map_name, m.mode, m.is_ranked,
               COALESCE((SELECT json_agg(json_build_object(
                            'team_id', t.team_id, 'outcome', t.outcome, 'score', t.score)
                            ORDER BY t.team_id)
                         FROM match_teams t WHERE t.match_id = m.match_id), '[]'::json),
               json_agg(json_build_object(
                   'xuid', mp.xuid::text, 'gamertag', p.gamertag, 'team_id', mp.team_id,
                   'outcome', mp.outcome, 'kills', mp.kills, 'deaths', mp.deaths,
                   'assists', mp.assists, 'damage_dealt', mp.damage_dealt,
                   'personal_score', mp.personal_score)
                   ORDER BY mp.team_id, mp.xuid)
        FROM matches m
        JOIN match_players mp ON mp.match_id = m.match_id
        JOIN players p ON p.xuid = mp.xuid
        WHERE m.start_time >= %s AND m.start_time < %s AND mp.xuid = ANY(%s)
        GROUP BY m.match_id
        ORDER BY m.start_time
    """
    with connection() as conn:
        rows = conn.execute(sql, (since, until, ids)).fetchall()
    return [{"match_id": str(r[0]), "start_time": r[1], "map": r[2], "mode": r[3],
             "ranked": r[4], "teams": r[5], "players": r[6]} for r in rows]


# ==============================
# Ingestion log
# ==============================
def start_run(source):
    with connection() as conn:
        return conn.execute("INSERT INTO ingest_runs (source) VALUES (%s) RETURNING id",
                            (source,)).fetchone()[0]


def finish_run(run_id, status, new_matches=0, new_rows=0, errors=0):
    with connection() as conn:
        conn.execute("UPDATE ingest_runs SET finished_at = now(), status = %s, new_matches = %s, "
                     "new_rows = %s, errors = %s WHERE id = %s",
                     (status, new_matches, new_rows, errors, run_id))


# ==============================
# Stats snapshots
# ==============================
SNAPSHOT_COLS = ("xuid", "snapshot_date", "season", "matches", "wins", "losses", "kills",
                 "deaths", "assists", "damage_dealt", "damage_taken", "accuracy",
                 "time_played_s", "row", "record")


def today_cdmx():
    return dt.datetime.now(CDMX).date()


def save_snapshots(snapshots, overwrite=True):
    """snapshots: dicts with SNAPSHOT_COLS. Same player + day + season: the newest run wins
    (overwrite=True) or the existing row is kept (overwrite=False, used by the Sheets import)."""
    cols = ", ".join(SNAPSHOT_COLS)
    marks = ", ".join(["%s"] * len(SNAPSHOT_COLS))
    if overwrite:
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in SNAPSHOT_COLS[3:])
        conflict = f"DO UPDATE SET {updates}, taken_at = now()"
    else:
        conflict = "DO NOTHING"
    sql = (f"INSERT INTO stats_snapshots ({cols}) VALUES ({marks}) "
           f"ON CONFLICT (xuid, snapshot_date, season) {conflict}")
    n = 0
    with connection() as conn, conn.transaction():
        for s in snapshots:
            vals = [s.get(c) for c in SNAPSHOT_COLS]
            vals[0] = int(vals[0])
            vals[2] = vals[2] or ""
            vals[13] = _jsonb(vals[13])
            vals[14] = _jsonb(vals[14])
            n += conn.execute(sql, vals).rowcount
    return n


# ==============================
# Night awards (Phase 3)
# ==============================
def active_members():
    """{xuid str: gamertag} of the active members, as last synced from Sheets."""
    with connection() as conn:
        rows = conn.execute("SELECT xuid, gamertag FROM players WHERE active").fetchall()
    return {str(x): gt for x, gt in rows}


def player_totals(xuids, since, until):
    """Sum of every match (any playlist, solo or with the group) per member in [since, until).
    {xuid str: {"games", "kills", "deaths", "assists"}}"""
    ids = [int(x) for x in xuids]
    if not ids:
        return {}
    sql = """
        SELECT xuid, count(*), sum(kills), sum(deaths), sum(assists)
        FROM match_players
        WHERE xuid = ANY(%s) AND start_time >= %s AND start_time < %s AND kills IS NOT NULL
        GROUP BY xuid
    """
    with connection() as conn:
        rows = conn.execute(sql, (ids, since, until)).fetchall()
    return {str(r[0]): {"games": r[1], "kills": r[2] or 0, "deaths": r[3] or 0,
                        "assists": r[4] or 0} for r in rows}


def claim_awards(night_date, games, payload, message):
    """Reserves the night. True only for the first caller: that one posts."""
    with connection() as conn:
        cur = conn.execute(
            "INSERT INTO night_awards (night_date, games, payload, message) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (night_date, games, _jsonb(payload), message))
        return cur.rowcount == 1


def release_awards(night_date):
    """Undo claim_awards() when posting to GroupMe failed, so the next run retries."""
    with connection() as conn:
        conn.execute("DELETE FROM night_awards WHERE night_date = %s", (night_date,))


def awards_for(night_date):
    with connection() as conn:
        row = conn.execute("SELECT games, payload, message, posted_at FROM night_awards "
                           "WHERE night_date = %s", (night_date,)).fetchone()
    return None if row is None else {"games": row[0], "payload": row[1], "message": row[2],
                                     "posted_at": row[3]}


# ==============================
# Player page (Phase 3)
# ==============================
TZ_NAME = "America/Mexico_City"


def find_player(gamertag):
    """(xuid str, gamertag, active) matching ignoring case and spaces, or None.
    An active member wins over an ex-member with the same name."""
    key = "".join((gamertag or "").lower().split())
    if not key:
        return None
    with connection() as conn:
        row = conn.execute(
            "SELECT xuid, gamertag, active FROM players "
            "WHERE lower(replace(gamertag, ' ', '')) = %s ORDER BY active DESC LIMIT 1",
            (key,)).fetchone()
    return None if row is None else (str(row[0]), row[1], row[2])


_SUMS = """count(*) AS games,
           count(*) FILTER (WHERE mp.outcome = 'win') AS wins,
           coalesce(sum(mp.kills), 0), coalesce(sum(mp.deaths), 0), coalesce(sum(mp.assists), 0),
           coalesce(sum(mp.damage_dealt), 0), coalesce(sum(mp.damage_taken), 0),
           coalesce(sum(mp.shots_hit), 0), coalesce(sum(mp.shots_fired), 0),
           coalesce(sum(mp.personal_score), 0)"""
_SUM_KEYS = ("games", "wins", "kills", "deaths", "assists", "damage_dealt", "damage_taken",
             "shots_hit", "shots_fired", "score")


def _sums(row, offset=0):
    return dict(zip(_SUM_KEYS, (int(v or 0) for v in row[offset:offset + len(_SUM_KEYS)])))


def player_data(xuid, since, trend_since):
    """Everything the player page needs, as raw sums (player_page.py does the math).
    since: start of the long window (maps, modes, duos); trend_since: start of the trend."""
    x = int(xuid)
    out = {}
    with connection() as conn:
        out["daily"] = [
            {"day": r[0].isoformat(), **_sums(r, 1)} for r in conn.execute(
                f"SELECT (mp.start_time AT TIME ZONE '{TZ_NAME}')::date AS day, {_SUMS} "
                "FROM match_players mp WHERE mp.xuid = %s AND mp.start_time >= %s "
                "GROUP BY day ORDER BY day", (x, trend_since)).fetchall()]
        out["trend_totals"] = _sums(conn.execute(
            f"SELECT {_SUMS} FROM match_players mp WHERE mp.xuid = %s AND mp.start_time >= %s",
            (x, trend_since)).fetchone())
        out["totals"] = _sums(conn.execute(
            f"SELECT {_SUMS} FROM match_players mp WHERE mp.xuid = %s AND mp.start_time >= %s",
            (x, since)).fetchone())
        # Group average over the trend window (active members), for context
        out["group_totals"] = _sums(conn.execute(
            f"SELECT {_SUMS} FROM match_players mp JOIN players p ON p.xuid = mp.xuid "
            "WHERE p.active AND mp.start_time >= %s", (trend_since,)).fetchone())
        out["maps"] = [
            {"map": r[0], **_sums(r, 1)} for r in conn.execute(
                f"SELECT coalesce(m.map_name, '?'), {_SUMS} FROM match_players mp "
                "JOIN matches m ON m.match_id = mp.match_id "
                "WHERE mp.xuid = %s AND mp.start_time >= %s GROUP BY 1", (x, since)).fetchall()]
        out["modes"] = [
            {"mode": r[0], **_sums(r, 1)} for r in conn.execute(
                f"SELECT coalesce(m.mode, '?'), {_SUMS} FROM match_players mp "
                "JOIN matches m ON m.match_id = mp.match_id "
                "WHERE mp.xuid = %s AND mp.start_time >= %s GROUP BY 1", (x, since)).fetchall()]
        # Duos: other members on the same team in the same match
        out["duos"] = [
            {"gamertag": r[0], "active": r[1], "games": r[2], "wins": r[3], "kills": r[4],
             "deaths": r[5], "assists": r[6]} for r in conn.execute(
                "SELECT p.gamertag, p.active, count(*), "
                "count(*) FILTER (WHERE mp.outcome = 'win'), coalesce(sum(mp.kills), 0), "
                "coalesce(sum(mp.deaths), 0), coalesce(sum(mp.assists), 0) "
                "FROM match_players mp "
                "JOIN match_players o ON o.match_id = mp.match_id AND o.team_id = mp.team_id "
                "     AND o.xuid <> mp.xuid "
                "JOIN players p ON p.xuid = o.xuid "
                "WHERE mp.xuid = %s AND mp.start_time >= %s "
                "GROUP BY p.gamertag, p.active", (x, since)).fetchall()]
        out["recent"] = [
            {"start_time": r[0].isoformat(), "map": r[1], "mode": r[2], "outcome": r[3],
             "kills": r[4], "deaths": r[5], "assists": r[6], "damage_dealt": r[7],
             "team_score": r[8], "other_score": r[9], "match_id": str(r[10])}
            for r in conn.execute(
                "SELECT mp.start_time, m.map_name, m.mode, mp.outcome, mp.kills, mp.deaths, "
                "mp.assists, mp.damage_dealt, "
                "(SELECT t.score FROM match_teams t WHERE t.match_id = mp.match_id "
                " AND t.team_id = mp.team_id), "
                "(SELECT max(t.score) FROM match_teams t WHERE t.match_id = mp.match_id "
                " AND t.team_id IS DISTINCT FROM mp.team_id), mp.match_id "
                "FROM match_players mp JOIN matches m ON m.match_id = mp.match_id "
                "WHERE mp.xuid = %s ORDER BY mp.start_time DESC LIMIT 10", (x,)).fetchall()]
        last = conn.execute("SELECT max(start_time) FROM match_players WHERE xuid = %s",
                            (x,)).fetchone()[0]
        out["last_played"] = last.isoformat() if last else None
    return out
