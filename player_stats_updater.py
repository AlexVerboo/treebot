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


def _get(obj, *names):
    """Lee el primer atributo que exista (los nombres cambian entre versiones de SPNKr)."""
    for n in names:
        v = getattr(obj, n, None)
        if v is not None:
            return v
    return 0


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
        "obj_pg": _div(c.objectives_completed, n) if hasattr(c, "objectives_completed") else "",
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
            caps += _get(zs, "zone_captures", "stronghold_captures")
            dk += _get(zs, "zone_defensive_kills", "stronghold_defensive_kills")
            ok += _get(zs, "zone_offensive_kills", "stronghold_offensive_kills")
            zt += _secs(_get(zs, "total_zone_occupation_time", "stronghold_occupation_time") or None)
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
    from spnkr.models.refdata import GameVariantCategory

    def cat(name):
        return (getattr(GameVariantCategory, name, None)
                or getattr(GameVariantCategory, "MULTIPLAYER_" + name))

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
    ctf = await record(cat("CTF"))
    zones = [z for z in [await record(cat("KING_OF_THE_HILL")),
                         await record(cat("STRONGHOLDS")),
                         await record(cat("TOTAL_CONTROL"))] if z]
    ball = await record(cat("ODDBALL"))
    seed = await record(cat("STOCKPILE"))
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


LAST_PLAYED = "Last played"
CDMX = dt.timezone(dt.timedelta(hours=-6))


def ensure_roles_sheet(book, gamertags, last_played=None):
    """Mantiene la hoja Roles: Gamertag | Last played | una columna con casillas por rol.
    Agrega miembros nuevos, actualiza "Last played" y ordena por la conexión más reciente.
    Nunca borra los tags que ya estaban marcados."""
    last_played = last_played or {}
    ws, created = _worksheet(book, ROLES_SHEET, max(len(gamertags) + 10, 50),
                             len(roles.ROLES) + 6)
    if ws is None:
        log(f"(DRY RUN) Crearía la hoja {ROLES_SHEET} con {len(gamertags)} miembros")
        return
    rows = [] if created else ws.get_all_values()
    old_header = [sheets._clean(h) for h in rows[0]] if rows and any(rows[0]) else []

    # Columnas de rol: las que ya tiene la hoja (en su orden) + las de roles.py que falten
    role_cols = [h for h in old_header[1:] if h and h.lower() != LAST_PLAYED.lower()]
    for name in roles.role_names():
        if name.lower() not in (h.lower() for h in role_cols):
            role_cols.append(name)
    header = ["Gamertag", LAST_PLAYED] + role_cols

    # Lo que ya había, por gamertag
    people = {}
    for r in rows[1:]:
        gt = sheets._clean(r[0]) if r else ""
        if not gt:
            continue
        cells = dict(zip(old_header, r))
        people[gt.lower()] = {"gt": gt, "last": sheets._clean(cells.get(LAST_PLAYED, "")),
                              "tags": {h: sheets._clean(cells.get(h, "")).lower() in sheets.TRUTHY
                                       for h in role_cols}}
    added = 0
    for gt in gamertags:
        if gt.lower() not in people:
            people[gt.lower()] = {"gt": gt, "last": "", "tags": {}}
            added += 1
    for gt, when in last_played.items():
        if gt.lower() in people and when:
            people[gt.lower()]["last"] = when.astimezone(CDMX).strftime("%Y-%m-%d %H:%M")

    # Más reciente arriba; los que no tienen fecha al final ("AAAA-MM-DD HH:MM" ordena bien como texto)
    ordered = sorted([p for p in people.values() if p["last"]], key=lambda p: p["last"], reverse=True) + \
              sorted([p for p in people.values() if not p["last"]], key=lambda p: p["gt"].lower())

    values = [header] + [[p["gt"], p["last"]] + [bool(p["tags"].get(h)) for h in role_cols]
                         for p in ordered]
    if ws.row_count < len(values) + 5:
        ws.add_rows(len(values) + 5 - ws.row_count)
    if ws.col_count < len(header):
        ws.add_cols(len(header) - ws.col_count)
    ws.batch_clear([f"A1:{chr(ord('A') + max(len(header), len(old_header)) - 1)}{max(len(rows), len(values)) + 1}"])
    ws.update(range_name="A1", values=values, value_input_option="RAW")
    total = len(values)
    book.batch_update({"requests": [
        # Sin casillas en "Last played", casillas en los roles
        {"setDataValidation": {"range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": total + 50,
                                         "startColumnIndex": 1, "endColumnIndex": 2}}},
        {"setDataValidation": {
            "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": total,
                      "startColumnIndex": 2, "endColumnIndex": len(header)},
            "rule": {"condition": {"type": "BOOLEAN"}, "showCustomUi": True}}},
        {"repeatCell": {"range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat.textFormat.bold"}},
        {"updateSheetProperties": {"properties": {"sheetId": ws.id, "gridProperties": {
            "frozenRowCount": 1, "frozenColumnCount": 1}},
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}},
    ]})
    log(f"Hoja {ROLES_SHEET}: {len(ordered)} miembros ordenados por última partida"
        + (f", {added} nuevo(s)" if added else ""))


async def last_match_time(client, xuid):
    """Hora en que terminó su última partida (cualquier tipo), o None."""
    try:
        hist = await api(client.stats.get_match_history, xuid, 0, 1, "all")
    except Exception as e:
        log(f"    (última partida: {short_err(e)})")
        return None
    if not hist.results:
        return None
    info = hist.results[0].match_info
    return info.end_time or info.start_time


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
        rows_by_gt, last_played = {}, {}
        for xuid, gt in members.items():
            last_played[gt] = await last_match_time(client, xuid)
            try:
                rows_by_gt[gt] = await player_row(client, xuid)
                log(f"- {gt}: {rows_by_gt[gt]['matches']} partidas")
            except Exception as e:
                log(f"- {gt}: sin stats ({short_err(e)}: {e}). ¿Perfil privado?")

    book = sheets._get_book()
    gamertags = [r[sheets.COL_GAMERTAG].strip()
                 for r in sheets._values(sheets.MEMBERS_SHEET, use_cache=False)
                 if len(r) > sheets.COL_GAMERTAG and r[sheets.COL_GAMERTAG].strip()]
    ensure_roles_sheet(book, gamertags, last_played)
    write_stats(book, rows_by_gt)


if __name__ == "__main__":
    if sys.version_info < (3, 11):
        sys.exit("player_stats_updater.py necesita Python 3.11+ (SPNKr)")
    asyncio.run(main())
