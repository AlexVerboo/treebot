"""
Estadísticas por jugador para la página /roles.

Qué hace (una vez al día, desde GitHub Actions):
  1. Lee los gamertags de "Trees in Space Members" (columna AB).
  2. Se asegura de que exista la hoja "Roles" (una fila por miembro, una columna con
     casillas por rol). Solo agrega miembros nuevos: nunca borra los tags que ya pusiste.
  3. Pide a la API de Halo el service record de cada miembro (matchmaking, de por vida):
     el general y los de CTF, zonas (KOTH/Strongholds/Total Control), Oddball y Stockpile.
  4. Escribe todo en la hoja "Player Stats" (se reemplaza completa en cada corrida).

Usa las mismas variables de entorno que records_updater.py. Requiere Python 3.11+.
  STATS_SEASON   (opcional) id de temporada para limitar las stats a esa temporada
  DRY_RUN=1      (opcional) solo muestra, no escribe
"""

import asyncio
import datetime as dt
import os
import sys

import roles
import sheets
from records_updater import api, log, short_err, resolve_members, DRY_RUN

ROLES_SHEET = "Roles"
STATS_SHEET = "Player Stats"
SEASON = os.getenv("STATS_SEASON") or None

KEYS = list(roles.STATS)


def _div(a, b):
    return round(a / b, 3) if b else 0


def _secs(td):
    return td.total_seconds() if td else 0


def compute_row(overall, ctf, zones, ball, seed):
    """overall: ServiceRecord general; ctf/ball/seed: ServiceRecord o None; zones: lista."""
    c = overall.core_stats
    n = overall.matches_completed or 0
    row = {
        "matches": n,
        "win_pct": _div(overall.wins, n),
        "kills_pg": _div(c.kills, n),
        "deaths_pg": _div(c.deaths, n),
        "assists_pg": _div(c.assists, n),
        "kd": _div(c.kills, c.deaths) if c.deaths else c.kills,
        "kda": round(c.average_kda or 0, 3),
        "dmg_pg": _div(c.damage_dealt, n),
        "dmg_diff_pg": _div(c.damage_dealt - c.damage_taken, n),
        "accuracy": round((c.accuracy or 0) / 100, 4),
        "headshot_pct": _div(c.headshot_kills, c.kills),
        "power_kills_pg": _div(c.power_weapon_kills, n),
        "melee_kills_pg": _div(c.melee_kills, n),
        "max_spree": c.max_killing_spree,
        "callouts_pg": _div(c.callout_assists, n),
        "obj_pg": _div(c.objectives_completed, n),
        "driver_assists_pg": _div(c.driver_assists, n),
        "vehicle_destroys_pg": _div(c.vehicle_destroys, n),
        "hijacks_pg": _div(c.hijacks, n),
        "emp_assists_pg": _div(c.emp_assists, n),
    }

    s = ctf.capture_the_flag_stats if ctf else None
    m = ctf.matches_completed if ctf else 0
    row.update({
        "ctf_matches": m,
        "caps_pg": _div(s.flag_captures, m) if s else 0,
        "grabs_pg": _div(s.flag_grabs, m) if s else 0,
        "returns_pg": _div(s.flag_returns, m) if s else 0,
        "carrier_kills_pg": _div(s.flag_carriers_killed, m) if s else 0,
        "carry_time_pg": _div(_secs(s.time_as_flag_carrier), m) if s else 0,
    })

    zm = caps = dk = ok = zt = 0
    for z in zones:
        zs = z.zones_stats
        zm += z.matches_completed or 0
        if zs:
            caps += zs.stronghold_captures or 0
            dk += zs.stronghold_defensive_kills or 0
            ok += zs.stronghold_offensive_kills or 0
            zt += _secs(zs.stronghold_occupation_time)
    row.update({
        "zone_matches": zm,
        "zone_caps_pg": _div(caps, zm),
        "zone_def_kills_pg": _div(dk, zm),
        "zone_off_kills_pg": _div(ok, zm),
        "zone_time_pg": _div(zt, zm),
    })

    o = ball.oddball_stats if ball else None
    m = ball.matches_completed if ball else 0
    row.update({
        "ball_matches": m,
        "ball_time_pg": _div(_secs(o.time_as_skull_carrier), m) if o else 0,
        "ball_carrier_kills_pg": _div(o.skull_carriers_killed, m) if o else 0,
    })

    p = seed.stockpile_stats if seed else None
    m = seed.matches_completed if seed else 0
    row.update({
        "seed_matches": m,
        "seeds_dep_pg": _div(p.power_seeds_deposited, m) if p else 0,
        "seed_carrier_kills_pg": _div(p.power_seed_carriers_killed, m) if p else 0,
    })
    return row


async def player_row(client, xuid):
    from spnkr.models.refdata import GameVariantCategory as G

    async def record(category=None):
        try:
            return await api(client.stats.get_service_record, xuid, "matchmade",
                             season_id=SEASON, game_variant_category=category)
        except Exception as e:
            if category is None:
                raise
            log(f"    ({category.name}: {short_err(e)})")
            return None

    overall = await record()
    ctf = await record(G.MULTIPLAYER_CTF)
    zones = [z for z in [await record(G.MULTIPLAYER_KING_OF_THE_HILL),
                         await record(G.MULTIPLAYER_STRONGHOLDS),
                         await record(G.MULTIPLAYER_TOTAL_CONTROL)] if z]
    ball = await record(G.MULTIPLAYER_ODDBALL)
    seed = await record(G.MULTIPLAYER_STOCKPILE)
    return compute_row(overall, ctf, zones, ball, seed)


# ==============================
# Hojas
# ==============================
def _worksheet(book, name, rows, cols):
    import gspread
    try:
        return book.worksheet(name), False
    except gspread.WorksheetNotFound:
        if DRY_RUN:
            return None, True
        return book.add_worksheet(title=name, rows=rows, cols=cols), True


def ensure_roles_sheet(book, gamertags):
    """Crea la hoja Roles con casillas o agrega los miembros que falten."""
    header = ["Gamertag"] + roles.role_names()
    ws, created = _worksheet(book, ROLES_SHEET, max(len(gamertags) + 10, 50), len(header) + 4)
    if ws is None:
        log(f"(DRY RUN) Crearía la hoja {ROLES_SHEET} con {len(gamertags)} miembros")
        return
    rows = [] if created else ws.get_all_values()
    if not rows or not any(rows[0]):
        ws.update(range_name="A1", values=[header], value_input_option="RAW")
        rows = [header]
        ws.format("A1:Z1", {"textFormat": {"bold": True}})
        ws.freeze(rows=1, cols=1)
    have = {sheets._clean(r[0]).lower() for r in rows[1:] if r}
    width = max(len(rows[0]), len(header))
    new = [[gt] + [False] * (width - 1) for gt in gamertags if gt.lower() not in have]
    if new:
        start = len(rows) + 1
        ws.update(range_name=f"A{start}", values=new, value_input_option="RAW")
        log(f"Hoja {ROLES_SHEET}: {len(new)} miembro(s) agregado(s)")
    # Casillas en todas las columnas de roles (B en adelante)
    total = len(rows) + len(new)
    if total > 1:
        book.batch_update({"requests": [{"setDataValidation": {
            "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": total,
                      "startColumnIndex": 1, "endColumnIndex": width},
            "rule": {"condition": {"type": "BOOLEAN"}, "showCustomUi": True},
        }}]})


def write_stats(book, rows_by_gt):
    header = ["gamertag"] + KEYS
    values = [header] + [[gt] + [row.get(k, 0) for k in KEYS] for gt, row in rows_by_gt.items()]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    values.append(["updated", stamp])
    if DRY_RUN:
        for v in values[:4]:
            log(v)
        log(f"(DRY RUN) Escribiría {len(rows_by_gt)} jugadores en {STATS_SHEET}")
        return
    ws, _ = _worksheet(book, STATS_SHEET, len(values) + 10, len(header) + 2)
    ws.clear()
    ws.update(range_name="A1", values=values, value_input_option="RAW")
    log(f"Hoja {STATS_SHEET}: {len(rows_by_gt)} jugadores")


async def main():
    from aiohttp import ClientSession
    from spnkr import AzureApp, HaloInfiniteClient, refresh_player_tokens

    app = AzureApp(os.environ["AZURE_CLIENT_ID"], os.environ["AZURE_CLIENT_SECRET"],
                   "https://localhost")
    async with ClientSession() as session:
        player = await refresh_player_tokens(session, app, os.environ["HALO_REFRESH_TOKEN"])
        log(f"Sesión de Halo iniciada como {player.gamertag}")
        client = HaloInfiniteClient(session=session,
                                    spartan_token=player.spartan_token.token,
                                    clearance_token=player.clearance_token.token,
                                    requests_per_second=2)
        members = await resolve_members(client)
        rows_by_gt = {}
        for xuid, gt in members.items():
            try:
                rows_by_gt[gt] = await player_row(client, xuid)
                log(f"- {gt}: {rows_by_gt[gt]['matches']} partidas")
            except Exception as e:
                log(f"- {gt}: sin stats ({short_err(e)}). ¿Perfil privado?")

    book = sheets._get_book()
    gamertags = [r[sheets.COL_GAMERTAG].strip()
                 for r in sheets._values(sheets.MEMBERS_SHEET, use_cache=False)
                 if len(r) > sheets.COL_GAMERTAG and r[sheets.COL_GAMERTAG].strip()]
    ensure_roles_sheet(book, gamertags)
    write_stats(book, rows_by_gt)


if __name__ == "__main__":
    if sys.version_info < (3, 11):
        sys.exit("player_stats_updater.py necesita Python 3.11+ (SPNKr)")
    asyncio.run(main())
