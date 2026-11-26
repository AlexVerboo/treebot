"""
Halo Infinite login for the GitHub Actions scripts.

Why it exists: Microsoft refresh tokens expire (~90 days). Every login returns a
NEW refresh token, but SPNKr's refresh_player_tokens() throws it away, so the
HALO_REFRESH_TOKEN secret used to die on its own and every workflow failed
the same day. This module:

  1. Logs in with HALO_REFRESH_TOKEN (same steps as SPNKr).
  2. Saves the new refresh token back into the GitHub secret HALO_REFRESH_TOKEN,
     so it never expires as long as some workflow runs.
  3. Sends an alert to Discord if the login fails or the token cannot be saved.

Saving the secret needs GH_SECRETS_TOKEN: a fine-grained GitHub token, repo
treebot only, permission "Secrets: Read and write". Without it the bot works
exactly as before and sends an alert (at most once a day) reminding you.
"""

import base64
import os

import requests

import alerts

GH_REPO = os.getenv("GH_REPO") or os.getenv("GITHUB_REPOSITORY") or "AlexVerboo/treebot"
SECRET_NAME = "HALO_REFRESH_TOKEN"

RENEW_HELP = ("Run `python get_halo_token.py` on your computer and paste the new token "
              "into the GitHub secret HALO_REFRESH_TOKEN.")


def _log(msg):
    print(msg, flush=True)


def _mask(value):
    """Hides the value in GitHub Actions logs."""
    if value and os.getenv("GITHUB_ACTIONS"):
        print(f"::add-mask::{value}", flush=True)


def _pass_to_next_steps(new_token):
    """Later steps of the same job use the new token (the secret was read at job start)."""
    os.environ["HALO_REFRESH_TOKEN_NEW"] = new_token
    env_file = os.getenv("GITHUB_ENV")
    if env_file:
        try:
            with open(env_file, "a", encoding="utf-8") as fh:
                fh.write(f"HALO_REFRESH_TOKEN_NEW={new_token}\n")
        except OSError:
            pass


def save_refresh_token(new_token):
    """Writes the new refresh token into the HALO_REFRESH_TOKEN repo secret.
    Returns True if saved. Never raises."""
    gh_token = (os.getenv("GH_SECRETS_TOKEN") or "").strip()
    if not gh_token:
        _log("halo_auth: GH_SECRETS_TOKEN is not set, the renewed Halo token was not saved")
        alerts.send("The Halo token was renewed but could not be saved: GH_SECRETS_TOKEN is missing. "
                    "Without it, HALO_REFRESH_TOKEN will expire in ~90 days.",
                    key="halo-token-not-saved")
        return False
    try:
        from nacl import encoding, public
        headers = {"Authorization": f"Bearer {gh_token}",
                   "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        base = f"https://api.github.com/repos/{GH_REPO}/actions/secrets"
        r = requests.get(f"{base}/public-key", headers=headers, timeout=15)
        r.raise_for_status()
        key = r.json()
        box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
        encrypted = base64.b64encode(box.encrypt(new_token.encode())).decode()
        r = requests.put(f"{base}/{SECRET_NAME}", headers=headers, timeout=15,
                         json={"encrypted_value": encrypted, "key_id": key["key_id"]})
        r.raise_for_status()
        _log("halo_auth: HALO_REFRESH_TOKEN renewed in GitHub")
        return True
    except Exception as e:  # noqa: BLE001 - must never break the workflow
        _log(f"halo_auth: could not save the renewed token ({type(e).__name__}: {e})")
        alerts.send(f"The Halo token was renewed but saving it to GitHub failed "
                    f"({type(e).__name__}). Check that GH_SECRETS_TOKEN has "
                    f"'Secrets: Read and write' on {GH_REPO}.",
                    key="halo-token-not-saved")
        return False


async def login(session, app=None, refresh_token=None, save=True):
    """Same as spnkr.refresh_player_tokens(), but keeps the renewed refresh token.
    Returns spnkr's AuthenticatedPlayer."""
    from spnkr import AzureApp
    from spnkr.auth import halo, oauth, player, xbox
    from spnkr.auth.core import XSTS_V3_HALO_AUDIENCE, XSTS_V3_XBOX_AUDIENCE

    app = app or AzureApp(os.environ["AZURE_CLIENT_ID"], os.environ["AZURE_CLIENT_SECRET"],
                          "https://localhost")
    # HALO_REFRESH_TOKEN_NEW: token renewed by an earlier step of the same workflow
    old_token = (refresh_token or os.getenv("HALO_REFRESH_TOKEN_NEW")
                 or os.environ["HALO_REFRESH_TOKEN"])
    try:
        oauth_token = await oauth.refresh_oauth_token(session, old_token, app)
        user_token = await xbox.request_user_token(session, oauth_token.access_token)
        xsts_token = await xbox.request_xsts_token(session, user_token.token, XSTS_V3_XBOX_AUDIENCE)
        halo_xsts = await xbox.request_xsts_token(session, user_token.token, XSTS_V3_HALO_AUDIENCE)
        spartan_token = await halo.request_spartan_token(session, halo_xsts.token)
        clearance_token = await halo.request_clearance_token(session, spartan_token.token)
    except Exception as e:
        alerts.send(f"Halo login failed ({type(e).__name__}: {str(e)[:200]}). {RENEW_HELP}",
                    key="halo-login")
        raise

    new_token = (oauth_token.raw or {}).get("refresh_token")
    if new_token and new_token != old_token:
        _mask(new_token)
        _pass_to_next_steps(new_token)
        if save:
            save_refresh_token(new_token)

    return player.AuthenticatedPlayer(
        player_id=xsts_token.xuid,
        gamertag=xsts_token.gamertag,
        spartan_token=spartan_token,
        clearance_token=clearance_token,
        xbl_authorization_header_value=xsts_token.authorization_header_value,
    )
