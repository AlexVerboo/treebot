"""
Agrega un miembro nuevo: lo busca en Xbox (para usar el gamertag exacto) y lo escribe
en la columna AB de "Trees in Space Members" y en la hoja "Roles".

Se corre desde GitHub Actions: workflow "Add member" (pide el gamertag).
Mismas variables de entorno que records_updater.py. Requiere Python 3.11+.
"""

import asyncio
import os
import sys

import sheets
from records_updater import api, log, short_err
from player_stats_updater import ensure_roles_sheet


async def xbox_gamertag(gamertag):
    from aiohttp import ClientSession
    from spnkr import AzureApp, HaloInfiniteClient, refresh_player_tokens

    app = AzureApp(os.environ["AZURE_CLIENT_ID"], os.environ["AZURE_CLIENT_SECRET"],
                   "https://localhost")
    async with ClientSession() as session:
        player = await refresh_player_tokens(session, app, os.environ["HALO_REFRESH_TOKEN"])
        client = HaloInfiniteClient(session=session,
                                    spartan_token=player.spartan_token.token,
                                    clearance_token=player.clearance_token.token)
        user = await api(client.profile.get_user_by_gamertag, gamertag)
        return user.gamertag


def main(gamertag):
    try:
        gamertag = asyncio.run(xbox_gamertag(gamertag))
        log(f"Encontrado en Xbox como '{gamertag}'")
    except Exception as e:
        sys.exit(f"No encontré '{gamertag}' en Xbox ({short_err(e)}). Revisa cómo se escribe.")

    book = sheets._get_book()
    ws = book.worksheet(sheets.MEMBERS_SHEET)
    col = ws.col_values(sheets.COL_GAMERTAG + 1)
    current = [c.strip() for c in col if c.strip()]
    if gamertag.lower() in (c.lower() for c in current):
        log(f"'{gamertag}' ya estaba en {sheets.MEMBERS_SHEET}")
    else:
        last = max(i for i, c in enumerate(col, start=1) if c.strip())
        ws.update_cell(last + 1, sheets.COL_GAMERTAG + 1, gamertag)
        log(f"Agregado a {sheets.MEMBERS_SHEET}, fila {last + 1} (columna AB)")
        current.append(gamertag)
    ensure_roles_sheet(book, current)


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        sys.exit("Uso: python add_member.py \"Gamertag\"")
    main(sys.argv[1].strip())
