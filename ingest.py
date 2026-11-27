"""
Saves the members' new matches into Postgres (TreeBot v2.0).

    python ingest.py                          # last INGEST_HOURS hours for every member
    python ingest.py --source night           # same, labeled in ingest_runs
    python ingest.py --gamertag "X" --days 90 # backfill one member (Add member workflow)
    python ingest.py --days 60                # backfill everyone

How it avoids asking Halo twice for the same match:
  1. For each member, read the match history (cheap: 25 matches per call) back to the
     lookback limit. This gives "member X played match M".
  2. Ask the DB which (match, member) rows already exist.
  3. Only matches with a missing row are requested with get_match_stats (the expensive
     call). For an old member a stored match always has their row, so it is skipped.
     For a NEW member, matches that the group already stored are fetched once more to add
     only their row; every other row is left as it was (ON CONFLICT DO NOTHING).
  4. Each match (match + teams + member rows) is saved in one transaction.

New members are easy: anyone who appears in the Sheets members list for the first time (or
comes back) automatically gets INGEST_NEW_MEMBER_DAYS of history on the next run. The
"Add member" workflow also runs a backfill right away.

Only Trees in Space members are stored (not opponents).

Environment: DATABASE_URL plus the same Halo / Google variables as records_updater.py.
  INGEST_HOURS            (optional, default 48) normal lookback
  INGEST_NEW_MEMBER_DAYS  (optional, default 30) lookback for new / returning members
  INGEST_MAX_PAGES        (optional, default 40) history pages per member, 25 matches each
Requires Python 3.11+ (SPNKr).
"""

import argparse
import asyncio
import datetime as dt
import os
import re
import sys

import db
from records_updater import MODE_NAMES, api, clean_map_name, log, short_err

HOURS = float(os.getenv("INGEST_HOURS", "48"))
NEW_MEMBER_DAYS = float(os.getenv("INGEST_NEW_MEMBER_DAYS", "30"))
MAX_PAGES = int(os.getenv("INGEST_MAX_PAGES", "40"))
PAGE = 25
RANKED = re.compile(r"\s*-\s*ranked\b.*$", re.I)


# ==============================
# Pure helpers (tested without Halo or a database)
# ==============================
def xuid_of(player_id):
    return str(player_id).strip("xuid()")


def _name(enum_value):
    return enum_value.name.lower() if enum_value is not None else None


def _secs(td):
    return round(td.total_seconds()) if td is not None else None


def mode_name(category):
    """Same display name the GGs recap always used."""
    cat = category.name if hasattr(category, "name") else str(category)
    return (MODE_NAMES.get(cat) or MODE_NAMES.get("MULTIPLAYER_" + cat)
            or cat.replace("MULTIPLAYER_", "").replace("_", " ").title())


def _plain(value):
    """Pydantic model / dict -> JSON-friendly dict (timedeltas as seconds)."""
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dt.timedelta):
        return round(value.total_seconds(), 1)
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if hasattr(value, "name") and hasattr(value, "value"):      # enums
        return value.name
    if hasattr(value, "hex") and not isinstance(value, (int, float, str)):  # UUID
        return str(value)
    return value


MODE_STAT_FIELDS = ("capture_the_flag_stats", "oddball_stats", "zones_stats", "stockpile_stats",
                    "elimination_stats", "extraction_stats", "infection_stats", "bomb_stats")


def match_row(stats, map_raw="", playlist_raw=""):
    info = stats.match_info
    ranked = "ranked" in (map_raw or "").lower()   # same rule as the v1 GGs recap
    return {
        "match_id": str(stats.match_id),
        "start_time": info.start_time,
        "end_time": info.end_time,
        "duration_s": _secs(info.duration),
        "map_asset_id": info.map_variant.asset_id if info.map_variant else None,
        "map_version_id": info.map_variant.version_id if info.map_variant else None,
        "map_name": clean_map_name(RANKED.sub("", map_raw or "")) or None,
        "mode": mode_name(info.game_variant_category),
        "mode_category": getattr(info.game_variant_category, "name", None),
        "playlist_id": info.playlist.asset_id if info.playlist else None,
        "playlist_name": playlist_raw or None,
        "lifecycle": _name(info.lifecycle_mode),
        "is_ranked": ranked,
        "season_id": getattr(info, "season_id", None),
    }


def team_rows(stats):
    return [{"match_id": str(stats.match_id), "team_id": t.team_id, "outcome": _name(t.outcome),
             "rank": t.rank, "score": t.stats.core_stats.score} for t in stats.teams]


def player_rows(stats, members):
    """Rows for the members (and only the members) who played this match."""
    rows = []
    for p in stats.players:
        x = xuid_of(p.player_id)
        if x not in members:
            continue
        team_stats = p.player_team_stats[0].stats if p.player_team_stats else None
        c = team_stats.core_stats if team_stats else None
        part = p.participation_info
        mode_stats = {}
        for field in MODE_STAT_FIELDS:
            value = getattr(team_stats, field, None) if team_stats else None
            if value is not None:
                mode_stats[field.replace("_stats", "")] = _plain(value)
        row = {
            "match_id": str(stats.match_id), "xuid": x,
            "start_time": stats.match_info.start_time,
            "team_id": p.last_team_id, "outcome": _name(p.outcome), "rank": p.rank,
            "time_played_s": _secs(part.time_played) if part else None,
            "joined_in_progress": part.joined_in_progress if part else None,
            "present_at_completion": part.present_at_completion if part else None,
            "mode_stats": mode_stats or None,
            "medals": {str(m.name_id): m.count for m in c.medals} if c else None,
        }
        if c:
            for k in ("kills", "deaths", "assists", "damage_dealt", "damage_taken", "shots_fired",
                      "shots_hit", "score", "personal_score", "headshot_kills", "melee_kills",
                      "grenade_kills", "power_weapon_kills", "callout_assists",
                      "max_killing_spree", "driver_assists", "vehicle_destroys", "hijacks"):
                row[k] = getattr(c, k, None)
            row["accuracy"] = round(c.accuracy, 2) if c.accuracy is not None else None
        rows.append(row)
    return rows


def plan_fetch(seen, existing):
    """seen: {match_id: {member xuids whose history lists it}}; existing: {(match_id, xuid)}.
    Returns the match ids that still miss at least one member row."""
    return [m for m, xuids in seen.items() if any((m, x) not in existing for x in xuids)]


# ==============================
# Halo
# ==============================
async def member_history(client, xuid, since, max_pages=MAX_PAGES):
    """{match_id: start_time} for this member since `since` (newest pages first)."""
    found, start = {}, 0
    for _ in range(max_pages):
        page = await api(client.stats.get_match_history, xuid, start=start, count=PAGE,
                         match_type="all")
        recent = [m for m in page.results if m.match_info.start_time >= since]
        for m in recent:
            found[str(m.match_id)] = m.match_info.start_time
        if len(recent) < len(page.results) or len(page.results) < PAGE:
            break
        start += PAGE
    return found


class _Names:
    """Map / playlist names, cached for the run (few distinct maps)."""

    def __init__(self, client):
        self.client = client
        self.cache = {}

    async def get(self, kind, asset):
        if asset is None:
            return ""
        key = (kind, asset.asset_id, asset.version_id)
        if key not in self.cache:
            svc = self.client.discovery_ugc
            fn = svc.get_map if kind == "map" else svc.get_playlist
            try:
                self.cache[key] = (await api(fn, asset.asset_id, asset.version_id)).public_name
            except Exception as e:
                log(f"  (could not read a {kind} name: {short_err(e)})")
                self.cache[key] = ""
        return self.cache[key]


async def run(client, members, source="manual", hours=None, days=None, only=None):
    """Ingests matches for `members` ({xuid: gamertag}). `only`: gamertag to backfill alone.
    Returns {"new_matches", "new_rows", "fetched", "errors"}."""
    now = dt.datetime.now(dt.timezone.utc)
    if only:
        target = {x: gt for x, gt in members.items() if gt.lower() == only.lower()}
        if not target:
            raise SystemExit(f"'{only}' is not in the members list (Sheets).")
    else:
        target = members

    newcomers = set(db.sync_players(members))
    if newcomers:
        log(f"New or returning members: {', '.join(members[x] for x in newcomers)}")

    default_since = now - (dt.timedelta(days=days) if days else dt.timedelta(hours=hours or HOURS))
    newcomer_since = min(default_since, now - dt.timedelta(days=NEW_MEMBER_DAYS))

    run_id = db.start_run(source)
    result = {"new_matches": 0, "new_rows": 0, "fetched": 0, "errors": 0}
    try:
        seen, start_times = {}, {}
        for xuid, gt in target.items():
            since = newcomer_since if xuid in newcomers else default_since
            try:
                found = await member_history(client, xuid, since)
            except Exception as e:
                log(f"- {gt}: history unavailable ({short_err(e)}). Private?")
                result["errors"] += 1
                continue
            for mid, when in found.items():
                seen.setdefault(mid, set()).add(xuid)
                start_times[mid] = when
        existing = db.existing_rows(list(seen))
        todo = sorted(plan_fetch(seen, existing), key=start_times.get)
        log(f"{len(seen)} matches in the members' history, {len(todo)} to fetch from Halo")

        names = _Names(client)
        for mid in todo:
            try:
                stats = await api(client.stats.get_match_stats, mid)
            except Exception as e:
                log(f"  (could not read match {mid}: {short_err(e)})")
                result["errors"] += 1
                continue
            result["fetched"] += 1
            info = stats.match_info
            match = match_row(stats, await names.get("map", info.map_variant),
                              await names.get("playlist", info.playlist))
            new, added = db.save_match(match, team_rows(stats), player_rows(stats, members))
            result["new_matches"] += new
            result["new_rows"] += added
    except Exception:
        db.finish_run(run_id, "failed", result["new_matches"], result["new_rows"],
                      result["errors"] + 1)
        raise
    status = "ok" if not result["errors"] else "partial"
    db.finish_run(run_id, status, result["new_matches"], result["new_rows"], result["errors"])
    log(f"Ingest ({source}): {result['new_matches']} new matches, {result['new_rows']} new "
        f"player rows, {result['fetched']} fetched from Halo, {result['errors']} errors")
    return result


async def main(args):
    from aiohttp import ClientSession
    from spnkr import AzureApp, HaloInfiniteClient
    import halo_auth
    from records_updater import resolve_members

    app = AzureApp(os.environ["AZURE_CLIENT_ID"], os.environ["AZURE_CLIENT_SECRET"],
                   "https://localhost")
    async with ClientSession() as session:
        player = await halo_auth.login(session, app)
        log(f"Halo session started as {player.gamertag}")
        client = HaloInfiniteClient(session=session,
                                    spartan_token=player.spartan_token.token,
                                    clearance_token=player.clearance_token.token,
                                    requests_per_second=4)
        members = await resolve_members(client)
        log(f"{len(members)} members")
        await run(client, members, source=args.source, hours=args.hours, days=args.days,
                  only=args.gamertag)


def parse_args(argv):
    p = argparse.ArgumentParser(description="Save the members' new matches into Postgres")
    p.add_argument("--source", default="manual",
                   choices=["daily", "night", "ggs", "backfill", "manual"])
    p.add_argument("--hours", type=float, default=None, help=f"lookback (default {HOURS:g})")
    p.add_argument("--days", type=float, default=None, help="lookback in days (backfill)")
    p.add_argument("--gamertag", default=None, help="backfill only this member")
    return p.parse_args(argv)


if __name__ == "__main__":
    if sys.version_info < (3, 11):
        sys.exit("ingest.py needs Python 3.11+ (SPNKr)")
    if not db.enabled():
        log("DATABASE_URL is not set: skipping ingestion.")
        sys.exit(0)
    arguments = parse_args(sys.argv[1:])
    if arguments.gamertag and not arguments.gamertag.strip():
        arguments.gamertag = None
    try:
        asyncio.run(main(arguments))
    except SystemExit:
        raise
    except Exception as e:
        log(f"Ingest failed: {e!r}")
        raise
