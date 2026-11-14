"""
Resumen de las partidas de esta noche, para el comando "ggs" de GroupMe.

Cómo funciona:
  1. En GroupMe alguien escribe "ggs".
  2. El bot (app.py, en Render) contesta "crunching..." y arranca el workflow
     "GGs summary" de GitHub Actions (necesita GH_DISPATCH_TOKEN en Render).
  3. Este script busca las partidas de las últimas GGS_HOURS horas en las que jugaron
     al menos GGS_MIN_PLAYERS miembros en el mismo equipo y manda el resumen a GroupMe.

Variables de entorno: las mismas que records_updater.py, más
  GGS_HOURS         (opcional, default 10) cuántas horas hacia atrás cuentan como "esta noche"
  GGS_MIN_PLAYERS   (opcional, default 2) miembros mínimos juntos para contar la partida
  DRY_RUN=1         (opcional) imprime el resumen sin mandarlo a GroupMe
Requiere Python 3.11+ (SPNKr).
"""

import asyncio
import datetime as dt
import os
import sys

import requests

from records_updater import (MODE_NAMES, api, clean_map_name, log, resolve_members,
                             short_err)

HOURS = float(os.getenv("GGS_HOURS", "10"))
MIN_PLAYERS = int(os.getenv("GGS_MIN_PLAYERS", "2"))
DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
HISTORY_PAGE = 25


def post(text):
    bot_id = os.getenv("GROUPME_BOT_ID")
    if DRY_RUN or not bot_id:
        log("---- GroupMe ----\n" + text)
        return
    for i in range(0, max(len(text), 1), 990):
        requests.post("https://api.groupme.com/v3/bots/post",
                      json={"bot_id": bot_id, "text": text[i:i + 990]},
                      timeout=10).raise_for_status()


def xuid_of(player_id):
    return player_id.strip("xuid()")


async def tonight_matches(client, members, since):
    """IDs de partidas desde `since` en las que jugó algún miembro."""
    ids = {}
    for xuid, gt in members.items():
        start = 0
        while True:
            try:
                page = await api(client.stats.get_match_history, xuid, start=start,
                                 count=HISTORY_PAGE, match_type="all")
            except Exception as e:
                log(f"- {gt}: historial no disponible ({short_err(e)})")
                break
            recent = [m for m in page.results if m.match_info.start_time >= since]
            for m in recent:
                ids[str(m.match_id)] = m.match_info.start_time
            if len(recent) < len(page.results) or len(page.results) < HISTORY_PAGE:
                break
            start += HISTORY_PAGE
    return sorted(ids, key=ids.get)


async def build_summary(client, members, since):
    from spnkr.models.refdata import Outcome

    names = {}

    async def map_name(asset):
        key = (asset.asset_id, asset.version_id)
        if key not in names:
            try:
                names[key] = (await api(client.discovery_ugc.get_map,
                                        asset.asset_id, asset.version_id)).public_name
            except Exception:
                names[key] = "?"
        return names[key]

    games, totals = [], {}
    for mid in await tonight_matches(client, members, since):
        try:
            stats = await api(client.stats.get_match_stats, mid)
        except Exception as e:
            log(f"  (no pude leer la partida {mid}: {short_err(e)})")
            continue
        ours = [p for p in stats.players if xuid_of(p.player_id) in members]
        if not ours:
            continue
        # el equipo donde jugaron más miembros
        by_team = {}
        for p in ours:
            by_team.setdefault(p.last_team_id, []).append(p)
        team_id, squad = max(by_team.items(), key=lambda kv: len(kv[1]))
        if len(squad) < MIN_PLAYERS:
            continue

        info = stats.match_info
        cat = info.game_variant_category.name
        mode = (MODE_NAMES.get(cat) or MODE_NAMES.get("MULTIPLAYER_" + cat)
                or cat.replace("MULTIPLAYER_", "").replace("_", " ").title())
        team = next((t for t in stats.teams if t.team_id == team_id), None)
        others = [t for t in stats.teams if t.team_id != team_id]
        outcome = team.outcome if team else squad[0].outcome
        mine = team.stats.core_stats.score if team else 0
        theirs = max((t.stats.core_stats.score for t in others), default=0)
        games.append({
            "win": outcome == Outcome.WIN, "tie": outcome == Outcome.TIE,
            "map": clean_map_name(await map_name(info.map_variant)), "mode": mode,
            "score": f"{mine}-{theirs}",
        })

        for p in squad:
            gt = members[xuid_of(p.player_id)]
            core = p.player_team_stats[0].stats.core_stats if p.player_team_stats else None
            if core is None:
                continue
            t = totals.setdefault(gt, {"games": 0, "wins": 0, "kills": 0, "deaths": 0,
                                       "assists": 0, "damage": 0})
            t["games"] += 1
            t["wins"] += outcome == Outcome.WIN
            t["kills"] += core.kills
            t["deaths"] += core.deaths
            t["assists"] += core.assists
            t["damage"] += core.damage_dealt
    return games, totals


def format_summary(games, totals):
    if not games:
        return (f"No Trees in Space games in the last {HOURS:g} hours 🌴😴 "
                "(I only count games with 2+ Trees on the same team)")
    wins = sum(g["win"] for g in games)
    ties = sum(g["tie"] for g in games)
    losses = len(games) - wins - ties
    record = f"{wins}W - {losses}L" + (f" - {ties}T" if ties else "")
    out = [f"🌴 GGs! Tonight's recap: {len(games)} games, {record}", ""]
    for g in games[-15:]:
        icon = "✅" if g["win"] else ("➖" if g["tie"] else "❌")
        out.append(f"{icon} {g['mode']} on {g['map']} ({g['score']})")
    if len(games) > 15:
        out.append(f"…and {len(games) - 15} earlier games")

    if totals:
        def kd(t):
            return t["kills"] / max(t["deaths"], 1)
        most = lambda key: max(totals.items(), key=lambda kv: kv[1][key])
        out.append("")
        gt, t = most("kills")
        out.append(f"🔥 Most kills: {gt} ({t['kills']})")
        gt, t = max(totals.items(), key=lambda kv: (kv[1]["games"] >= 2, kd(kv[1])))
        out.append(f"🎯 Best K/D: {gt} ({kd(t):.2f})")
        gt, t = most("assists")
        out.append(f"🤝 Most assists: {gt} ({t['assists']})")
        gt, t = most("damage")
        out.append(f"💥 Most damage: {gt} ({t['damage']:,})")
        gt, t = most("deaths")
        out.append(f"💀 Most deaths: {gt} ({t['deaths']}) — thanks for your sacrifice")
    return "\n".join(out)


async def main():
    from aiohttp import ClientSession
    from spnkr import AzureApp, HaloInfiniteClient, refresh_player_tokens

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=HOURS)
    app = AzureApp(os.environ["AZURE_CLIENT_ID"], os.environ["AZURE_CLIENT_SECRET"],
                   "https://localhost")
    async with ClientSession() as session:
        player = await refresh_player_tokens(session, app, os.environ["HALO_REFRESH_TOKEN"])
        client = HaloInfiniteClient(session=session,
                                    spartan_token=player.spartan_token.token,
                                    clearance_token=player.clearance_token.token,
                                    requests_per_second=4)
        members = await resolve_members(client)
        games, totals = await build_summary(client, members, since)
    post(format_summary(games, totals))


if __name__ == "__main__":
    if sys.version_info < (3, 11):
        sys.exit("ggs_summary.py necesita Python 3.11+ (SPNKr)")
    try:
        asyncio.run(main())
    except Exception as e:
        log(f"Error: {e!r}")
        post("I tried to count tonight's games but Halo's servers said no 🌴💥 try again in a bit")
        raise
