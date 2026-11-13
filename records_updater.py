"""
Actualizador automático de récords de Trees in Space.

Qué hace:
  1. Se conecta a la API (no oficial) de Halo Infinite con SPNKr.
  2. Revisa las partidas recientes de matchmaking de los miembros del grupo.
  3. Si el grupo ganó una partida de Big Team, Squad Battle o Heavies con al menos
     MIN_GROUP_PLAYERS miembros en el equipo, la compara con el récord de ese mapa+modo.
  4. Si es mejor (más rápida, o margen mayor en Slayer), actualiza la hoja de Google:
     el récord anterior pasa a "Good Times" y el nuevo queda como "Best Times".
  5. Avisa en GroupMe.

Se corre desde GitHub Actions (ver .github/workflows/update-records.yml). Requiere Python 3.11+.

Variables de entorno:
  GOOGLE_CREDENTIALS_JSON   JSON de la cuenta de servicio de Google
  AZURE_CLIENT_ID           App de Azure para iniciar sesión en Xbox
  AZURE_CLIENT_SECRET
  HALO_REFRESH_TOKEN        Se obtiene una vez con get_halo_token.py
  GROUPME_BOT_ID            (opcional) para avisar en el chat
  MIN_GROUP_PLAYERS         (opcional, default 5) miembros mínimos en el equipo ganador
  MATCHES_PER_PLAYER        (opcional, default 25) partidas recientes a revisar por miembro
  DRY_RUN=1                 (opcional) solo muestra lo que haría, sin escribir
"""

import asyncio
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass

import requests

import sheets

MIN_GROUP_PLAYERS = int(os.getenv("MIN_GROUP_PLAYERS", "5"))
MATCHES_PER_PLAYER = int(os.getenv("MATCHES_PER_PLAYER", "25"))
DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
MATCH_URL = "https://halotracker.com/halo-infinite/match/{}"

# Nombre del modo como aparece en la hoja, según la categoría que reporta la API
MODE_NAMES = {
    "MULTIPLAYER_SLAYER": "Slayer",
    "MULTIPLAYER_CTF": "Capture the Flag",
    "MULTIPLAYER_TOTAL_CONTROL": "Total Control",
    "MULTIPLAYER_STOCKPILE": "Stockpile",
    "MULTIPLAYER_KING_OF_THE_HILL": "King of the Hill",
    "MULTIPLAYER_ODDBALL": "Oddball",
    "MULTIPLAYER_STRONGHOLDS": "Strongholds",
    "MULTIPLAYER_EXTRACTION": "Extraction",
    "MULTIPLAYER_ESCORT": "Escort",
    "MULTIPLAYER_ASSAULT": "Assault",
    "MULTIPLAYER_ATTRITION": "Attrition",
    "MULTIPLAYER_ELIMINATION": "Elimination",
}
SCORE_MODES = {"slayer"}           # se mide por marcador (margen); el resto por tiempo
MODE_ALIASES = {"ctf": "capture the flag"}


def log(msg):
    print(msg, flush=True)


# ==============================
# Clasificación y comparación
# ==============================
def kind_for_playlist(name):
    """Qué hoja corresponde a la playlist de la partida (None = no se registra)."""
    n = (name or "").lower()
    if "heav" in n:
        return "heavies"
    if "squad" in n:
        return "squad"
    if "big team" in n or "btb" in n:
        return "btb"
    return None


def norm_mode(mode):
    m = (mode or "").strip().lower()
    return MODE_ALIASES.get(m, m)


def norm_map(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def parse_result(mode, value):
    """Convierte lo que hay en la hoja a un número comparable (más alto = mejor).
    Tiempo -> -segundos; Slayer -> margen. None si no se entiende."""
    v = (value or "").strip().lower()
    if not v or v == "---":
        return None
    if norm_mode(mode) in SCORE_MODES:
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", v)
        return int(m.group(1)) - int(m.group(2)) if m else None
    if "/" in v:                                   # "3-0 / 11:48"
        v = v.split("/")[-1].strip()
    m = re.fullmatch(r"(\d+)m\s*(\d+)s", v)        # "24m 17s"
    if m:
        return -(int(m.group(1)) * 60 + int(m.group(2)))
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(?:00)?)?", v)  # "2:32", "2:32:00", "3:19:"
    if m:
        return -(int(m.group(1)) * 60 + int(m.group(2)))
    return None


def format_duration(td):
    secs = int(round(td.total_seconds()))
    return f"{secs // 60}:{secs % 60:02d}"


@dataclass
class Candidate:
    kind: str
    map: str
    mode: str
    result: str
    value: int
    date: str
    link: str
    match_id: str
    members: list


# ==============================
# Escritura en la hoja
# ==============================
class RecordSheet:
    """Envuelve una hoja de récords (bloque Best en A-F, Good en G-L)."""

    def __init__(self, worksheet):
        self.ws = worksheet
        self.rows = worksheet.get_all_values()

    def _cell(self, r, c):
        row = self.rows[r] if r < len(self.rows) else []
        return row[c].strip() if c < len(row) else ""

    def maps(self):
        return {self._cell(r, 2) for r in range(len(self.rows)) if self._cell(r, 2)}

    def resolve_map(self, api_name):
        """Usa el nombre que ya existe en la hoja si se parece (ej. Deadlock ~ DEATHLOCK)."""
        import difflib
        existing = {norm_map(m): m for m in self.maps() if m.lower() != "map"}
        key = norm_map(api_name)
        if key in existing:
            return existing[key]
        close = difflib.get_close_matches(key, list(existing), n=1, cutoff=0.75)
        return existing[close[0]] if close else api_name

    def find_best(self, mapa, mode):
        for r in range(len(self.rows)):
            if (norm_map(self._cell(r, 2)) == norm_map(mapa)
                    and norm_mode(self._cell(r, 1)) == norm_mode(mode)):
                return r
        return None

    def _first_empty(self, start_col):
        for r in range(2, len(self.rows) + 1):
            if all(not self._cell(r, c) for c in range(start_col, start_col + 6)):
                return r
        return len(self.rows)

    def _write(self, r, start_col, values):
        col_a = chr(ord("A") + start_col)
        col_b = chr(ord("A") + start_col + len(values) - 1)
        rng = f"{col_a}{r + 1}:{col_b}{r + 1}"
        if not DRY_RUN:
            self.ws.update(range_name=rng, values=[values], value_input_option="RAW")
        while len(self.rows) <= r:
            self.rows.append([])
        row = self.rows[r] + [""] * (start_col + len(values) - len(self.rows[r]))
        row[start_col:start_col + len(values)] = values
        self.rows[r] = row

    def apply(self, cand):
        """Escribe el récord si es mejor. Devuelve el texto del récord anterior, '' si era
        el primero, o None si no hubo cambio."""
        r = self.find_best(cand.map, cand.mode)
        if r is None:
            row = self._first_empty(0)
            self._write(row, 0, [cand.date, cand.mode, cand.map, cand.result, "", cand.link])
            return ""
        old = [self._cell(r, c) for c in range(6)]
        old_value = parse_result(old[1], old[3])
        if old_value is None:                        # celda vacía o "---": se llena
            self._write(r, 0, [cand.date, old[1], old[2], cand.result, old[4], cand.link])
            return ""
        if cand.value <= old_value or self._cell(r, 5) == cand.link:
            return None
        good_row = self._first_empty(6)
        self._write(good_row, 6, old)                # el récord anterior pasa a Good Times
        self._write(r, 0, [cand.date, old[1], old[2], cand.result, old[4], cand.link])
        return old[3]


# ==============================
# Halo Infinite API
# ==============================
async def api(fn, *args, **kwargs):
    """Llama a la API y la parsea; reintenta si Halo responde 429 (demasiadas peticiones) o 5xx."""
    from aiohttp import ClientResponseError
    for attempt in range(6):
        try:
            return await (await fn(*args, **kwargs)).parse()
        except ClientResponseError as e:
            if e.status == 429 or e.status >= 500:
                wait = 2 ** attempt
                try:
                    wait = max(wait, float((e.headers or {}).get("Retry-After", 0)))
                except (TypeError, ValueError):
                    pass
                await asyncio.sleep(wait)
                continue
            raise
    raise RuntimeError("Halo siguió respondiendo 429/5xx después de varios intentos")


def short_err(e):
    status = getattr(e, "status", None)
    return f"HTTP {status}" if status else type(e).__name__


MAP_SUFFIXES = re.compile(r"\s*[-–:]?\s*\b(heavies|one flag|ctf|capture the flag|btb|big team|"
                          r"slayer|stockpile|total control|king of the hill|koth|oddball|strongholds)\b.*$",
                          re.I)


def clean_map_name(name):
    """'Refuge Heavies' -> 'Refuge'; 'Breaker One Flag CTF' -> 'Breaker'."""
    cleaned = MAP_SUFFIXES.sub("", name or "").strip()
    return cleaned or (name or "").strip()


async def collect_candidates(client, members):
    """members: {xuid_str: gamertag}. Devuelve candidatos a récord, uno por partida."""
    from spnkr.models.refdata import LifecycleMode, Outcome

    seen, candidates = set(), []
    names = {"map": {}, "playlist": {}, "variant": {}}

    async def asset_name(kind, asset):
        key = (asset.asset_id, asset.version_id)
        if key not in names[kind]:
            svc = client.discovery_ugc
            fn = {"map": svc.get_map, "playlist": svc.get_playlist,
                  "variant": svc.get_ugc_game_variant}[kind]
            try:
                names[kind][key] = (await api(fn, asset.asset_id, asset.version_id)).public_name
            except Exception as e:
                log(f"  (no pude leer el nombre de un {kind}: {short_err(e)})")
                names[kind][key] = ""
        return names[kind][key]

    for xuid, gamertag in members.items():
        try:
            history = await api(client.stats.get_match_history, xuid, count=MATCHES_PER_PLAYER,
                                match_type="matchmaking")
        except Exception as e:
            log(f"- {gamertag}: historial no disponible ({short_err(e)}). ¿Es privado?")
            continue
        log(f"- {gamertag}: {len(history.results)} partidas recientes")

        for item in history.results:
            mid = str(item.match_id)
            if mid in seen:
                continue
            seen.add(mid)
            info = item.match_info
            if info.lifecycle_mode != LifecycleMode.MATCHMADE or item.outcome != Outcome.WIN:
                continue
            if info.playlist is None:
                continue
            playlist_name = await asset_name("playlist", info.playlist)
            kind = kind_for_playlist(playlist_name)
            if not kind:
                continue
            map_raw = await asset_name("map", info.map_variant)
            variant = await asset_name("variant", info.ugc_game_variant)
            if "heav" in f"{map_raw} {variant}".lower():
                kind = "heavies"

            try:
                stats = await api(client.stats.get_match_stats, mid)
            except Exception as e:
                log(f"  (no pude leer la partida {mid}: {short_err(e)})")
                continue
            win_team = next((t for t in stats.teams if t.outcome == Outcome.WIN), None)
            if win_team is None:
                continue
            ours = [members[p.player_id.strip("xuid()")] for p in stats.players
                    if p.last_team_id == win_team.team_id
                    and p.player_id.strip("xuid()") in members]
            if len(ours) < MIN_GROUP_PLAYERS:
                continue

            category = info.game_variant_category.name
            mode = MODE_NAMES.get(category)
            if "one flag" in f"{variant} {map_raw}".lower():
                mode = "One Flag"
            if not mode:
                continue
            mapa = clean_map_name(map_raw)
            if not mapa:
                continue

            if norm_mode(mode) in SCORE_MODES:
                other = [t for t in stats.teams if t.team_id != win_team.team_id]
                mine = win_team.stats.core_stats.score
                theirs = max((t.stats.core_stats.score for t in other), default=0)
                result, value = f"{mine}-{theirs}", mine - theirs
            else:
                result = format_duration(info.duration)
                value = -int(round(info.duration.total_seconds()))

            candidates.append(Candidate(
                kind=kind, map=mapa, mode=mode, result=result, value=value,
                date=info.start_time.astimezone(dt.timezone(dt.timedelta(hours=-6))).strftime("%d/%m/%Y"),
                link=MATCH_URL.format(mid), match_id=mid, members=sorted(ours),
            ))
    return candidates


async def resolve_members(client):
    rows = sheets._values(sheets.MEMBERS_SHEET, use_cache=False)
    gamertags = [r[sheets.COL_GAMERTAG].strip() for r in rows
                 if len(r) > sheets.COL_GAMERTAG and r[sheets.COL_GAMERTAG].strip()]
    members = {}
    for gt in gamertags:
        try:
            user = await api(client.profile.get_user_by_gamertag, gt)
            members[str(user.xuid)] = gt
        except Exception as e:
            log(f"- No encontré el gamertag '{gt}' en Xbox ({short_err(e)}). ¿Lo cambió?")
    return members


def notify(text):
    bot_id = os.getenv("GROUPME_BOT_ID")
    if not bot_id or DRY_RUN:
        return
    try:
        requests.post("https://api.groupme.com/v3/bots/post",
                      json={"bot_id": bot_id, "text": text}, timeout=10).raise_for_status()
    except requests.RequestException as e:
        log(f"No pude avisar en GroupMe: {e!r}")


LABELS = {"btb": "Big Team", "squad": "Squad Battle", "heavies": "Heavies"}


def apply_candidates(candidates, open_sheet):
    """Aplica los candidatos a las hojas. open_sheet(kind) -> RecordSheet."""
    changes = []
    sheets_by_kind = {}
    # Primero los mejores, para que cada mapa+modo quede con el mejor de esta corrida
    for cand in sorted(candidates, key=lambda c: -c.value):
        if cand.kind not in sheets_by_kind:
            sheets_by_kind[cand.kind] = open_sheet(cand.kind)
        sheet = sheets_by_kind[cand.kind]
        cand.map = sheet.resolve_map(cand.map)
        before = sheet.apply(cand)
        if before is None:
            continue
        changes.append((cand, before))
    return changes


def announce(changes):
    for cand, before in changes:
        prev = f" (antes {sheets._clean_result(before)})" if before else " (primer récord de este mapa)"
        msg = (f"🏆 NEW {LABELS[cand.kind].upper()} RECORD!\n"
               f"{cand.map} – {cand.mode}: {cand.result}{prev}\n"
               f"Trees: {', '.join(cand.members)}\n{cand.link}")
        log(msg)
        notify(msg)


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
        log(f"{len(members)} miembros encontrados en Xbox")
        candidates = await collect_candidates(client, members)

    log(f"{len(candidates)} victorias del grupo en Big Team / Squad / Heavies")
    book = sheets._get_book()
    changes = apply_candidates(
        candidates, lambda kind: RecordSheet(book.worksheet(sheets.RECORD_SHEETS[kind])))
    announce(changes)
    log(f"Listo: {len(changes)} récord(s) nuevo(s){' (DRY RUN, sin escribir)' if DRY_RUN else ''}")


if __name__ == "__main__":
    if sys.version_info < (3, 11):
        sys.exit("records_updater.py necesita Python 3.11+ (SPNKr)")
    asyncio.run(main())
