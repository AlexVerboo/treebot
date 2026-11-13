# ==============================
# ACCESO A GOOGLE SHEETS
# ==============================
# Todas las lecturas/escrituras a "Trees in space game Records" viven aquí.
#
# Credenciales (en este orden):
#   1. GOOGLE_CREDENTIALS_JSON  -> el contenido completo del JSON de la cuenta de servicio
#   2. GOOGLE_APPLICATION_CREDENTIALS -> ruta a un archivo JSON (útil en local)
# Nunca subas el JSON al repo.

import os
import re
import json
import time
import random
import difflib

import gspread

SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "Trees in space game Records")

# Hojas de records y la etiqueta que se muestra en el bot / web
RECORD_SHEETS = {
    "btb": "Best Times",
    "squad": "Squad Battle Best Times",
    "heavies": "Heavies",
}

MEMBERS_SHEET = "Trees in Space Members"
IMAGES_SHEET = "Images"
DAYS_OFF_SHEET = "Unofficial Medals"
ROLES_SHEET = "Roles"
PLAYER_STATS_SHEET = "Player Stats"

# Columnas (base 0) en la hoja de miembros
COL_PROFILE_URL = 9    # J
COL_GAMERTAG = 27      # AB
COL_GROUPME_NAME = 28  # AC
COL_GROUPME_ID = 29    # AD

_client = None
_book = None
_cache = {}
CACHE_SECONDS = int(os.getenv("SHEETS_CACHE_SECONDS", "300"))


# ------------------------------
# Conexión
# ------------------------------
def _get_book():
    global _client, _book
    if _book is None:
        raw = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if raw:
            _client = gspread.service_account_from_dict(json.loads(raw))
        else:
            _client = gspread.service_account(
                filename=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "client_secret.json")
            )
        _book = _client.open(SPREADSHEET_NAME)
    return _book


def _values(sheet_name, use_cache=True):
    """Todas las celdas de una hoja como lista de filas (con caché corta)."""
    now = time.time()
    hit = _cache.get(sheet_name)
    if use_cache and hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    rows = _get_book().worksheet(sheet_name).get_all_values()
    _cache[sheet_name] = (now, rows)
    return rows


def clear_cache():
    _cache.clear()


# ------------------------------
# Limpieza de datos
# ------------------------------
def _clean(s):
    return (s or "").strip()


def _clean_date(s):
    s = _clean(s)
    if s in ("", "---"):
        return ""
    # Fechas que Sheets exportó como número de serie (ej. 44941)
    if s.isdigit() and 30000 < int(s) < 60000:
        from datetime import date, timedelta
        return (date(1899, 12, 30) + timedelta(days=int(s))).strftime("%d/%m/%Y")
    return s


def _clean_result(s):
    """'2:32:00' (minutos capturados como horas) -> '2:32'; '3:19:' -> '3:19'."""
    s = _clean(s)
    if s == "---":
        return ""
    m = re.fullmatch(r"(\d{1,2}):(\d{2}):(00)?", s)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    return s


def _parse_records(rows):
    """Cada hoja de records tiene dos bloques lado a lado:
    columnas A-F = Best Times, G-L = Good Times (Date, Mode, Map, Time, Image, Link)."""
    out = []
    for row in rows:
        for offset, tier in ((0, "best"), (6, "good")):
            cells = (row + [""] * 12)[offset:offset + 6]
            date, mode, mapa, result, _img, link = cells
            mode, mapa = _clean(mode), _clean(mapa)
            if not mode or not mapa or _clean(date).lower() == "date":
                continue
            if not _clean(result) or _clean(result) == "---":
                continue
            out.append({
                "tier": tier,
                "date": _clean_date(date),
                "mode": mode,
                "map": mapa,
                "result": _clean_result(result),
                "link": _clean(link) if _clean(link).startswith("http") else "",
            })
    return out


def get_records(kind="btb"):
    return _parse_records(_values(RECORD_SHEETS[kind]))


def get_members():
    """Lista pública de miembros: solo gamertag y perfil (sin IDs de GroupMe)."""
    rows = _values(MEMBERS_SHEET)
    profiles = [_clean(r[COL_PROFILE_URL]) for r in rows[2:]
                if len(r) > COL_PROFILE_URL and _clean(r[COL_PROFILE_URL]).startswith("http")]
    members = []
    for r in rows:
        if len(r) > COL_GAMERTAG and _clean(r[COL_GAMERTAG]):
            gt = _clean(r[COL_GAMERTAG])
            members.append({
                "gamertag": gt,
                "profile": _profile_for(gt, profiles),
            })
    return members


def _optional_values(sheet_name):
    """Como _values, pero devuelve [] si la hoja todavía no existe."""
    try:
        return _values(sheet_name)
    except gspread.WorksheetNotFound:
        return []


TRUTHY = {"true", "x", "yes", "si", "sí", "1", "✔", "✓", "✅"}


def get_roles():
    """Hoja "Roles": columna A = gamertag, una columna por rol (casilla o "x").
    Devuelve (lista de roles en el orden de la hoja, {gamertag: [roles]})."""
    rows = _optional_values(ROLES_SHEET)
    if not rows:
        return [], {}
    header = [_clean(h) for h in rows[0]]
    names = [h for h in header[1:] if h]
    tags = {}
    for r in rows[1:]:
        if not r or not _clean(r[0]):
            continue
        tags[_clean(r[0])] = [header[i] for i in range(1, min(len(r), len(header)))
                              if header[i] and _clean(r[i]).lower() in TRUTHY]
    return names, tags


def get_player_stats():
    """Hoja "Player Stats" (la escribe player_stats_updater.py).
    Devuelve ({gamertag: {stat: número}}, fecha de actualización)."""
    rows = _optional_values(PLAYER_STATS_SHEET)
    if not rows:
        return {}, ""
    header = [_clean(h) for h in rows[0]]
    stats, updated = {}, ""
    for r in rows[1:]:
        if not r or not _clean(r[0]):
            continue
        if _clean(r[0]).lower() == "updated":
            updated = _clean(r[1]) if len(r) > 1 else ""
            continue
        row = {}
        for k, v in zip(header[1:], r[1:]):
            try:
                row[k] = float(str(v).replace(",", ""))
            except ValueError:
                pass
        stats[_clean(r[0])] = row
    return stats, updated


def _profile_for(gamertag, profiles):
    from urllib.parse import unquote
    key = gamertag.lower().replace(" ", "")
    for url in profiles:
        m = re.search(r"/xbl/([^/]+)/", url)
        if m and unquote(m.group(1)).lower().replace(" ", "") == key:
            return url
    return ("https://halotracker.com/halo-infinite/profile/xbl/"
            + gamertag.replace(" ", "%20") + "/overview")


# ------------------------------
# Funciones que usa el bot
# ------------------------------
def _close_match(query, options):
    query = query.lower().strip()
    lowered = {o.lower().strip(): o for o in options if o}
    if query in lowered:
        return lowered[query]
    m = difflib.get_close_matches(query, list(lowered), n=1, cutoff=0.6)
    return lowered[m[0]] if m else None


def format_records(kind, query):
    records = get_records(kind)
    label = {"btb": "Big Team", "squad": "Squad Battle", "heavies": "Heavies"}[kind]
    query = query.strip()
    if not query:
        maps = sorted({r["map"] for r in records}, key=str.lower)
        return f"Usage: {kind_command(kind)} <map or game mode>\nMaps: " + ", ".join(maps)

    mapa = _close_match(query, [r["map"] for r in records])
    if mapa:
        rows = [r for r in records if r["map"].lower() == mapa.lower()]
        out = f"These are the {label} records for MAP {mapa}\n"
        for r in rows:
            out += f"{'🏆' if r['tier'] == 'best' else '👍'} {r['mode']} ➡️ {r['result']}\n"
        return out

    mode = _close_match(query, [r["mode"] for r in records])
    if mode:
        rows = [r for r in records if r["mode"].lower() == mode.lower()]
        out = f"These are the {label} records for GAMEMODE {mode}\n"
        for r in rows:
            out += f"{'🏆' if r['tier'] == 'best' else '👍'} {r['map']} ➡️ {r['result']}\n"
        return out

    return f"Yeah, dude, I dont see that one on the {label} maps or game modes"


def kind_command(kind):
    return {"btb": "records!", "squad": "squadrecords!", "heavies": "heavyrecords!"}[kind]


def random_image():
    rows = [r[0] for r in _values(IMAGES_SHEET) if r and _clean(r[0]).startswith("http")]
    idx = random.randrange(len(rows))
    return idx + 1, rows[idx]


def personal_stats(sender_id):
    rows = _values(MEMBERS_SHEET)
    gamertag = None
    for r in rows:
        if len(r) > COL_GROUPME_ID and _clean(r[COL_GROUPME_ID]) == str(sender_id):
            gamertag = _clean(r[COL_GAMERTAG])
            break
    if not gamertag:
        return "I dont see your name on the Stats list. Tell my boss to update his shit.... NEXT!!!"

    # Columnas C:I traen las stats; si la fórmula de halotracker falla salen como #VALUE!
    header = (rows[1] + [""] * 9)[2:9] if len(rows) > 1 else []
    for r in rows[2:]:
        cells = (r + [""] * 9)[2:9]
        if _clean(cells[0]).lower() == gamertag.lower():
            out = f"These are the stats for {gamertag}\n"
            for h, v in zip(header, cells):
                out += f"{h} ➡️ {v}\n"
            return out

    profile = _profile_for(gamertag, [_clean(r[COL_PROFILE_URL]) for r in rows[2:]
                                      if len(r) > COL_PROFILE_URL])
    return (f"{gamertag}, the stats table is broken right now (halotracker stopped feeding the sheet). "
            f"Check your profile here: {profile}")


def days_off():
    lines = [_clean(r[0]) for r in _values(DAYS_OFF_SHEET) if r and _clean(r[0])]
    return "\n".join(lines) if lines else "No days off registered."


def update_name(old_name, new_name):
    """Cuando GroupMe avisa 'X changed name to Y', actualiza la columna AC."""
    ws = _get_book().worksheet(MEMBERS_SHEET)
    col = ws.col_values(COL_GROUPME_NAME + 1)
    for i, value in enumerate(col, start=1):
        if _clean(value).lower() == old_name.strip().lower():
            ws.update_cell(i, COL_GROUPME_NAME + 1, new_name.strip())
            _cache.pop(MEMBERS_SHEET, None)
            return f"I will update {old_name} to {new_name}"
    return "For starters, I dont know who you are, you may want to add your name to the list"
