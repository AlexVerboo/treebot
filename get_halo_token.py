"""
Corre esto UNA vez en tu computadora para obtener el HALO_REFRESH_TOKEN.

  pip install spnkr
  python get_halo_token.py

Te pide el Client ID y el Secret de tu app de Azure, abre una página de Microsoft
para iniciar sesión con tu cuenta de Xbox, y al final imprime el refresh token.
Guárdalo como secreto HALO_REFRESH_TOKEN en GitHub (no lo subas al repo).
"""

import asyncio
import getpass

from aiohttp import ClientSession
from spnkr import AzureApp, authenticate_player, refresh_player_tokens


async def main():
    client_id = input("Azure Client ID: ").strip()
    client_secret = getpass.getpass("Azure Client Secret (no se ve al escribir): ").strip()
    app = AzureApp(client_id, client_secret, "https://localhost")
    async with ClientSession() as session:
        print("\n1) Abre en tu navegador el enlace que aparece abajo e inicia sesión con tu cuenta de Xbox.")
        print("2) Al terminar irás a https://localhost/?code=M.C5..._... (la página da error, es normal).")
        print("3) Copia solo lo que va después de 'code=' y pégalo aquí.\n")
        refresh_token = await authenticate_player(session, app)
        player = await refresh_player_tokens(session, app, refresh_token)
        print(f"\nListo, sesión iniciada como: {player.gamertag}")
        print("\nHALO_REFRESH_TOKEN (cópialo completo):\n")
        print(refresh_token)


if __name__ == "__main__":
    asyncio.run(main())
