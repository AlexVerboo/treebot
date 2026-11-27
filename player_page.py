"""
Numbers for the player page /player/<gamertag> and /api/player/<gamertag> (TreeBot v2.0, Phase 3).

db.player_data() returns raw sums (kills, deaths, games...) and this module turns them into
rates. Keeping the SQL simple (sums only) and the math in Python makes the math easy to test
without a database, and the same helpers will feed coach! in Phase 4.

Windows:
  PLAYER_TREND_DAYS      (default 30) the trend chart and the headline tiles
  PLAYER_WINDOW_DAYS     (default 90) maps, modes and duos (they need more games to mean something)
  PLAYER_DUO_MIN_GAMES   (default 5)  games together for a duo to be listed
  PLAYER_MAP_MIN_GAMES   (default 3)  games on a map / mode for it to count as strong or weak

Strong and weak maps are a private-ish view: they only show on the player's own page, never in
GroupMe (the Night awards post only positive things).
"""

import datetime as dt
import os
import threading
import time

import db

CACHE_TTL = 300
_cache = {}
_cache_lock = threading.Lock()


def config():
    def num(name, default):
        return int(os.getenv(name) or default)
    return {"trend_days": num("PLAYER_TREND_DAYS", 30),
            "window_days": num("PLAYER_WINDOW_DAYS", 90),
            "duo_min_games": num("PLAYER_DUO_MIN_GAMES", 5),
            "map_min_games": num("PLAYER_MAP_MIN_GAMES", 3)}


# ==============================
# Pure helpers
# ==============================
def rates(t):
    """Raw sums -> per-game rates. Safe with 0 games."""
    g = t.get("games") or 0
    k, d, a = t.get("kills", 0), t.get("deaths", 0), t.get("assists", 0)
    out = {"games": g, "wins": t.get("wins", 0), "losses": g - t.get("wins", 0)}
    if not g:
        return {**out, "win_pct": None, "kd": None, "kda_pg": None, "kills_pg": None,
                "deaths_pg": None, "assists_pg": None, "dmg_pg": None, "accuracy": None}
    hit, fired = t.get("shots_hit", 0), t.get("shots_fired", 0)
    out.update({
        "win_pct": round(100 * t.get("wins", 0) / g, 1),
        "kd": round(k / max(d, 1), 2),
        "kda_pg": round((k + a / 3 - d) / g, 2),          # Halo's KDA, per game
        "kills_pg": round(k / g, 2),
        "deaths_pg": round(d / g, 2),
        "assists_pg": round(a / g, 2),
        "dmg_pg": round(t["damage_dealt"] / g) if "damage_dealt" in t else None,
        "accuracy": round(100 * hit / fired, 1) if fired else None,
    })
    return out


def _rank_key(r):
    return (r["win_pct"] or 0, r["kda_pg"] or 0, r["games"])


def strong_weak(rows, name_key, min_games, n=3):
    """(all rows with rates sorted by games, strongest n, weakest n). Strong and weak never
    overlap, and with few qualified entries 'weak' stays empty rather than repeating them."""
    full = sorted(({name_key: r[name_key], **rates(r)} for r in rows),
                  key=lambda r: (-r["games"], str(r[name_key])))
    ok = sorted((r for r in full if r["games"] >= min_games), key=_rank_key, reverse=True)
    strong = ok[:n]
    rest = ok[len(strong):]
    weak = sorted(rest, key=_rank_key)[:n] if len(ok) > n else []
    return full, strong, weak


def duos(rows, min_games, n=5):
    out = []
    for r in rows:
        if r["games"] < min_games:
            continue
        out.append({"gamertag": r["gamertag"], "active": r["active"], **rates(r)})
    out.sort(key=_rank_key, reverse=True)
    return out[:n]


def build(raw, player, cfg, roles=(), profile=""):
    """The page's JSON. raw: db.player_data(); player: (xuid, gamertag, active)."""
    xuid, gamertag, active = player
    maps, strong_maps, weak_maps = strong_weak(raw["maps"], "map", cfg["map_min_games"])
    modes, strong_modes, weak_modes = strong_weak(raw["modes"], "mode", cfg["map_min_games"])
    recent = []
    for m in raw["recent"]:
        score = (f"{m['team_score']}-{m['other_score']}"
                 if m["team_score"] is not None and m["other_score"] is not None else "")
        recent.append({**m, "score": score})
    return {
        "gamertag": gamertag,
        "active": active,
        "roles": list(roles),
        "profile": profile,
        "last_played": raw["last_played"],
        "config": cfg,
        "trend_summary": rates(raw["trend_totals"]),
        "window_summary": rates(raw["totals"]),
        "group": rates(raw["group_totals"]),
        "trend": [{"day": d["day"], **rates(d)} for d in raw["daily"]],
        "maps": maps, "strong_maps": strong_maps, "weak_maps": weak_maps,
        "modes": modes, "strong_modes": strong_modes, "weak_modes": weak_modes,
        "duos": duos(raw["duos"], cfg["duo_min_games"]),
        "recent": recent,
        "updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
    }


# ==============================
# With the database
# ==============================
class NotFound(LookupError):
    pass


def load(gamertag, roles_for=None, profile_for=None, now=None):
    """Page data for a gamertag (cached CACHE_TTL seconds). Raises NotFound.
    roles_for / profile_for: callables gamertag -> roles list / profile URL (from Sheets)."""
    key = "".join((gamertag or "").lower().split())
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
    player = db.find_player(gamertag)
    if player is None:
        raise NotFound(gamertag)
    cfg = config()
    now = now or dt.datetime.now(dt.timezone.utc)
    raw = db.player_data(player[0], now - dt.timedelta(days=cfg["window_days"]),
                         now - dt.timedelta(days=cfg["trend_days"]))
    roles = profile = None
    try:
        roles = roles_for(player[1]) if roles_for else []
        profile = profile_for(player[1]) if profile_for else ""
    except Exception as e:                 # Sheets down: the page still works without them
        print(f"player page: Sheets unavailable ({e!r})", flush=True)
    data = build(raw, player, cfg, roles or [], profile or "")
    with _cache_lock:
        _cache[key] = (time.time(), data)
    return data


def clear_cache():
    with _cache_lock:
        _cache.clear()
