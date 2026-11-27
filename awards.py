"""
"Night awards": after a game night, post to GroupMe who stood out (TreeBot v2.0, Phase 3).

    python awards.py                      # tonight's (or last night's) awards
    python awards.py --night 2026-11-27   # a given night
    python awards.py --dry-run            # print, do not post or save
    python awards.py --force              # post even if that night was already posted

What counts as "the night": the Mexico City evening of night_date, from 16:00 to 10:00 the
next morning. The group plays roughly 8 pm - 1 am, so a session past midnight still belongs
to the evening it started. Run between 00:00 and 15:59 it means last night; from 16:00 on,
tonight.

Group games: same rule as the ggs recap: at least AWARDS_MIN_PLAYERS members on the same team.
Only the members on that team (the "squad") compete.

The three awards (only positive things go public):
  👑 MVP            highest personal score per game (Halo's own score: it counts kills,
                    assists AND objectives, so a flag runner can win it, not only a slayer).
                    Tie-break: KDA.
  📈 Most improved  biggest jump in KDA per game tonight vs. that player's own average of
                    the previous AWARDS_BASELINE_DAYS days (all their matches). Needs
                    AWARDS_BASELINE_MIN_GAMES games in that period. Not given to the MVP when
                    someone else also improved, and never given if nobody improved.
  🤝 Best duo       the pair with the best win % together tonight, with at least
                    AWARDS_DUO_MIN_GAMES games on the same team. Only shown at 50 % or more.
  To compete for MVP and most improved a player needs max(AWARDS_MIN_GAMES, half the group
  games) games that night, so one lucky game does not win.

KDA here is Halo's: kills + assists / 3 - deaths, per game.

Nothing is posted twice: the night is "claimed" in the night_awards table first, and only the
run that claimed it posts. If GroupMe fails, the claim is released so the next run retries.
Nothing is posted after AWARDS_DEADLINE_HOUR (Mexico City) of the next day: if the job ran
very late (GitHub's cron), the moment has passed.

Environment:
  DATABASE_URL, GROUPME_BOT_ID
  NIGHT_AWARDS=1                 turns the awards on (off by default)
  AWARDS_MIN_PLAYERS             default GGS_MIN_PLAYERS or 2
  AWARDS_MIN_GAMES               default 3
  AWARDS_DUO_MIN_GAMES           default 5
  AWARDS_BASELINE_DAYS           default 30
  AWARDS_BASELINE_MIN_GAMES      default 10
  AWARDS_DEADLINE_HOUR           default 12
  PUBLIC_URL                     default https://treesinspace.net (link to the player pages)
  DRY_RUN=1                      same as --dry-run
"""

import argparse
import datetime as dt
import os
import sys
from itertools import combinations

import requests

import alerts
import db

CDMX = db.CDMX
START_HOUR, END_HOUR = 16, 10


def _int(name, default):
    return int(os.getenv(name) or default)


def config():
    return {
        "min_players": _int("AWARDS_MIN_PLAYERS", os.getenv("GGS_MIN_PLAYERS") or 2),
        "min_games": _int("AWARDS_MIN_GAMES", 3),
        "duo_min_games": _int("AWARDS_DUO_MIN_GAMES", 5),
        "baseline_days": _int("AWARDS_BASELINE_DAYS", 30),
        "baseline_min_games": _int("AWARDS_BASELINE_MIN_GAMES", 10),
        "deadline_hour": _int("AWARDS_DEADLINE_HOUR", 12),
    }


def enabled():
    return os.getenv("NIGHT_AWARDS", "").strip().lower() in ("1", "true", "yes", "on")


def public_url():
    return (os.getenv("PUBLIC_URL") or "https://treesinspace.net").rstrip("/")


def log(msg):
    print(msg, flush=True)


# ==============================
# Pure helpers (tested without a database)
# ==============================
def night_of(now):
    """Mexico City date of the evening that `now` belongs to."""
    local = now.astimezone(CDMX)
    return local.date() if local.hour >= START_HOUR else local.date() - dt.timedelta(days=1)


def window(night_date):
    """(start, end) in UTC of that night."""
    start = dt.datetime.combine(night_date, dt.time(START_HOUR), CDMX)
    end = dt.datetime.combine(night_date + dt.timedelta(days=1), dt.time(END_HOUR), CDMX)
    return start.astimezone(dt.timezone.utc), end.astimezone(dt.timezone.utc)


def too_late(night_date, now, deadline_hour):
    deadline = dt.datetime.combine(night_date + dt.timedelta(days=1), dt.time(deadline_hour), CDMX)
    return now >= deadline


def kda(t):
    """Halo's KDA per game: (kills + assists / 3 - deaths) / games."""
    return (t["kills"] + t["assists"] / 3 - t["deaths"]) / t["games"] if t["games"] else 0.0


def squad_games(matches, min_players):
    """[(squad players, outcome)] for the group games (same rule as ggs)."""
    out = []
    for m in matches:
        by_team = {}
        for p in m["players"]:
            by_team.setdefault(p["team_id"], []).append(p)
        if not by_team:
            continue
        team_id, squad = max(by_team.items(), key=lambda kv: len(kv[1]))
        if len(squad) < min_players:
            continue
        team = next((t for t in m["teams"] if t["team_id"] == team_id), None)
        outcome = team["outcome"] if team else squad[0]["outcome"]
        out.append((squad, outcome))
    return out


def compute(matches, baseline, cfg):
    """matches: db.matches_since() rows of the night; baseline: db.player_totals() before it.
    Returns the payload (dict) or None when there were no group games."""
    games = squad_games(matches, cfg["min_players"])
    if not games:
        return None
    wins = sum(o == "win" for _, o in games)
    ties = sum(o == "tie" for _, o in games)
    payload = {"games": len(games), "wins": wins, "ties": ties,
               "losses": len(games) - wins - ties, "mvp": None, "improved": None, "duo": None}

    totals, names = {}, {}
    for squad, outcome in games:
        for p in squad:
            if p["kills"] is None:
                continue
            names[p["xuid"]] = p["gamertag"]
            t = totals.setdefault(p["xuid"], {"games": 0, "wins": 0, "kills": 0, "deaths": 0,
                                              "assists": 0, "score": 0})
            t["games"] += 1
            t["wins"] += outcome == "win"
            t["kills"] += p["kills"] or 0
            t["deaths"] += p["deaths"] or 0
            t["assists"] += p["assists"] or 0
            t["score"] += p.get("personal_score") or 0

    need = max(cfg["min_games"], (len(games) + 1) // 2)
    regulars = {x: t for x, t in totals.items() if t["games"] >= need}

    if regulars:
        x, t = max(regulars.items(), key=lambda kv: (kv[1]["score"] / kv[1]["games"], kda(kv[1])))
        payload["mvp"] = {"gamertag": names[x], "xuid": x, "games": t["games"],
                          "score_pg": round(t["score"] / t["games"]),
                          "kd": round(t["kills"] / max(t["deaths"], 1), 2),
                          "kda_pg": round(kda(t), 1)}

    improved = []
    for x, t in regulars.items():
        base = baseline.get(x)
        if not base or base["games"] < cfg["baseline_min_games"]:
            continue
        delta = kda(t) - kda(base)
        if delta > 0:
            improved.append((delta, x, t, base))
    improved.sort(key=lambda c: c[0], reverse=True)
    mvp_x = payload["mvp"]["xuid"] if payload["mvp"] else None
    pick = next((c for c in improved if c[1] != mvp_x), None) or (improved[0] if improved else None)
    if pick:
        delta, x, t, base = pick
        payload["improved"] = {"gamertag": names[x], "xuid": x, "games": t["games"],
                               "kda_pg": round(kda(t), 1), "baseline_kda_pg": round(kda(base), 1),
                               "delta": round(delta, 1), "baseline_games": base["games"]}

    pairs = {}
    for squad, outcome in games:
        ids = sorted({p["xuid"] for p in squad})
        for a, b in combinations(ids, 2):
            d = pairs.setdefault((a, b), {"games": 0, "wins": 0})
            d["games"] += 1
            d["wins"] += outcome == "win"
    duos = [(d["wins"] / d["games"], d["games"], k, d) for k, d in pairs.items()
            if d["games"] >= cfg["duo_min_games"]]
    if duos:
        rate, n, (a, b), d = max(duos, key=lambda c: (c[0], c[1]))
        if rate >= 0.5:
            pair = sorted([names.get(a, a), names.get(b, b)], key=str.lower)
            payload["duo"] = {"gamertags": pair, "games": n, "wins": d["wins"],
                              "losses": n - d["wins"], "win_pct": round(rate * 100)}
    return payload


def player_link(gamertag):
    from urllib.parse import quote
    return f"{public_url()}/player/{quote(gamertag)}"


def format_message(night_date, p):
    record = f"{p['wins']}W - {p['losses']}L" + (f" - {p['ties']}T" if p["ties"] else "")
    day = f"{night_date:%a %b} {night_date.day}"
    out = [f"🏆 Night awards ({day}): {p['games']} group games, {record}", ""]
    if p["mvp"]:
        m = p["mvp"]
        out.append(f"👑 MVP: {m['gamertag']} ({m['score_pg']:,} score/game, {m['kd']:.2f} K/D)")
    if p["improved"]:
        i = p["improved"]
        out.append(f"📈 Most improved: {i['gamertag']} (KDA {i['kda_pg']:+.1f}/game tonight "
                   f"vs. {i['baseline_kda_pg']:+.1f} their 30-day average)")
    if p["duo"]:
        d = p["duo"]
        out.append(f"🤝 Best duo: {d['gamertags'][0]} + {d['gamertags'][1]} "
                   f"({d['wins']}-{d['losses']} together, {d['win_pct']}%)")
    if p["mvp"]:
        out += ["", f"MVP page: {player_link(p['mvp']['gamertag'])}"]
    return "\n".join(out)


# ==============================
# Run
# ==============================
def post(text):
    bot_id = os.getenv("GROUPME_BOT_ID")
    if not bot_id:
        raise RuntimeError("GROUPME_BOT_ID is not set")
    for i in range(0, max(len(text), 1), 990):
        requests.post("https://api.groupme.com/v3/bots/post",
                      json={"bot_id": bot_id, "text": text[i:i + 990]},
                      timeout=10).raise_for_status()


def build(night_date, cfg=None):
    """(payload, message) for that night, or (None, None) without group games."""
    cfg = cfg or config()
    start, end = window(night_date)
    members = db.active_members()
    payload = compute(db.matches_since(start, list(members), until=end),
                      db.player_totals(list(members),
                                       start - dt.timedelta(days=cfg["baseline_days"]), start),
                      cfg)
    if payload is None:
        return None, None
    return payload, format_message(night_date, payload)


def run(night_date=None, now=None, dry_run=False, force=False, sender=post):
    """Returns what happened: 'off', 'too-late', 'no-games', 'no-awards', 'already-posted',
    'dry-run', 'posted'."""
    now = now or dt.datetime.now(dt.timezone.utc)
    night_date = night_date or night_of(now)
    cfg = config()
    if not (enabled() or dry_run or force):
        log("NIGHT_AWARDS is off: nothing to do.")
        return "off"
    if not (dry_run or force) and too_late(night_date, now, cfg["deadline_hour"]):
        log(f"Too late to post the awards of {night_date} (deadline "
            f"{cfg['deadline_hour']}:00 Mexico City the next day).")
        return "too-late"
    payload, message = build(night_date, cfg)
    if payload is None:
        log(f"No group games on the night of {night_date}: no awards.")
        return "no-games"
    if not (payload["mvp"] or payload["improved"] or payload["duo"]):
        log(f"{payload['games']} group games on {night_date}, but nobody played enough: no awards.")
        return "no-awards"
    log("---- Night awards ----\n" + message)
    if dry_run:
        return "dry-run"
    if force:
        db.release_awards(night_date)
    if not db.claim_awards(night_date, payload["games"], payload, message):
        log(f"The awards of {night_date} were already posted.")
        return "already-posted"
    try:
        sender(message)
    except Exception:
        db.release_awards(night_date)
        raise
    log("Posted to GroupMe.")
    return "posted"


def parse_args(argv):
    p = argparse.ArgumentParser(description="Post the Night awards to GroupMe")
    p.add_argument("--night", type=dt.date.fromisoformat, default=None,
                   help="evening date YYYY-MM-DD (Mexico City)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="post again even if already posted")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    dry = args.dry_run or os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
    if not db.enabled():
        log("DATABASE_URL is not set: no awards.")
        sys.exit(0)
    try:
        run(args.night, dry_run=dry, force=args.force)
    except Exception as e:
        log(f"Night awards failed: {e!r}")
        alerts.send(f"Night awards failed: {type(e).__name__}: {str(e)[:200]}", key="awards")
        raise
