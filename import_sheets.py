"""
One-time import from Google Sheets into Postgres (TreeBot v2.0, Phase 2).

    python import_sheets.py          # import
    DRY_RUN=1 python import_sheets.py

What it copies:
  - "XUIDs" (gamertag | xuid)  -> players. Active = still in "Trees in Space Members".
  - "Player Stats"              -> stats_snapshots, dated with the sheet's "updated" stamp
                                   (Mexico City day). Only the sheet row is known (per-game
                                   averages), so the total columns stay empty.

Safe to run again: existing players and snapshots are never overwritten (ON CONFLICT DO
NOTHING). Run migrate.py first. Needs DATABASE_URL and GOOGLE_CREDENTIALS_JSON.
"""

import datetime as dt
import os
import sys

import db
import sheets
from records_updater import XUID_SHEET, log

STATS_SHEET = "Player Stats"
DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")


def parse_players(xuid_rows, member_gamertags):
    """[(xuid, gamertag, active)] from the "XUIDs" sheet values (header in row 1)."""
    members = {g.strip().lower() for g in member_gamertags if g.strip()}
    out, seen = [], set()
    for r in xuid_rows[1:]:
        if len(r) < 2 or not str(r[0]).strip() or not str(r[1]).strip():
            continue
        gt, xuid = str(r[0]).strip(), str(r[1]).strip()
        if not xuid.isdigit() or xuid in seen:
            continue
        seen.add(xuid)
        out.append((int(xuid), gt, gt.lower() in members))
    return out


def _number(v):
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace(",", ".")
    try:
        f = float(s)
        return int(f) if f.is_integer() and "." not in s else f
    except ValueError:
        return s


def parse_stats(stats_rows):
    """({gamertag: row}, date | None) from "Player Stats" values (unformatted)."""
    if not stats_rows:
        return {}, None
    header = [str(h).strip() for h in stats_rows[0]]
    rows, date = {}, None
    for r in stats_rows[1:]:
        gt = str(r[0]).strip() if r else ""
        if not gt:
            continue
        if gt.lower() == "updated":
            try:
                stamp = dt.datetime.strptime(str(r[1]).strip(), "%Y-%m-%d %H:%M UTC")
                date = stamp.replace(tzinfo=dt.timezone.utc).astimezone(db.CDMX).date()
            except (IndexError, ValueError):
                pass
            continue
        rows[gt] = {k: _number(v) for k, v in zip(header[1:], r[1:]) if str(v).strip() != ""}
    return rows, date


def snapshots_from_sheet(stats_by_gt, date, players):
    xuid_by_gt = {gt.lower(): x for x, gt, _ in players}
    out, missing = [], []
    for gt, row in stats_by_gt.items():
        x = xuid_by_gt.get(gt.lower())
        if x is None:
            missing.append(gt)
            continue
        matches = row.get("matches")
        out.append({"xuid": x, "snapshot_date": date, "season": os.getenv("STATS_SEASON") or "",
                    "matches": matches if isinstance(matches, int) else None, "row": row})
    return out, missing


def main():
    if not db.enabled():
        sys.exit("DATABASE_URL is not set.")
    book = sheets._get_book()
    member_gts = [r[sheets.COL_GAMERTAG].strip()
                  for r in sheets._values(sheets.MEMBERS_SHEET, use_cache=False)
                  if len(r) > sheets.COL_GAMERTAG and r[sheets.COL_GAMERTAG].strip()]
    players = parse_players(book.worksheet(XUID_SHEET).get_all_values(), member_gts)
    log(f"{XUID_SHEET}: {len(players)} players ({sum(p[2] for p in players)} active)")

    stats_rows = book.worksheet(STATS_SHEET).get_all_values(value_render_option="UNFORMATTED_VALUE")
    stats_by_gt, date = parse_stats(stats_rows)
    date = date or db.today_cdmx()
    snaps, missing = snapshots_from_sheet(stats_by_gt, date, players)
    log(f"{STATS_SHEET}: {len(snaps)} rows dated {date}")
    if missing:
        log(f"  No xuid for: {', '.join(missing)} (skipped)")

    if DRY_RUN:
        log("(DRY RUN) nothing written")
        return
    added = db.import_players(players)
    saved = db.save_snapshots(snaps, overwrite=False)
    log(f"Done: {added} players added, {saved} snapshots added (existing rows kept).")


if __name__ == "__main__":
    main()
