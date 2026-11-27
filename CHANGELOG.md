# Changelog

## 2.0.0 (in development)

### Phase 0 — Assessment (26 Nov 2026)
- Data-flow map, weak points ranked by risk and dependency review. No code changes.

### Phase 1 — Stability
- **Python 3.11 everywhere.** Render now reads `.python-version` (it was on 3.7, unsupported since 2023). `runtime.txt` removed (Render ignored it). Flask 3.1, gunicorn 23, one gspread version (6.1.4) for the bot and the scripts.
- **GroupMe webhook answers immediately.** Commands run in a background thread (`gunicorn --threads 4`), so a slow spreadsheet no longer holds the request. Same commands, same replies.
- **Optional webhook secret** (`WEBHOOK_TOKEN`): when set, the callback URL must include `?token=...`.
- **`/health`** returns JSON (version, Python, uptime, config). `/health?deep=1` also checks Google Sheets.
- **Alerts to Discord** (`alerts.py`, `DISCORD_ALERT_WEBHOOK`): workflow failures, Halo login failures, Sheets errors and bot crashes, at most once every 10 min per kind.
- **The Halo token no longer expires.** `halo_auth.py` keeps the refresh token that Microsoft returns on every login and saves it into the `HALO_REFRESH_TOKEN` secret (needs `GH_SECRETS_TOKEN`).
- **The daily job runs on time.** The bot starts "Update Halo records" at 00:17 Mexico City (`scheduler.py`); GitHub's cron stays as a backup and skips itself if the job already ran.
- **Retries:** GroupMe posts (3 attempts) and Google Sheets (gspread `BackOffHTTPClient`).
- **Safer "Player Stats":** writes first and clears leftovers after (it used to clear the sheet first), and keeps yesterday's row for anyone Halo failed to answer for.
- **Tests:** 37 `pytest` tests and a CI workflow on every pull request.
- **Cleanup:** removed unused files (`app copy`, `prueba.py`, `local_tests.py`, `spreadsheet.py`, `Untitled-*`, `.vscode/`).

### Small fixes
- **One Flag records show the score too:** `3-0 / 11:48` (still ranked by time; old `11:48` rows compare fine).
- **snakemagic!** links to `https://snakemagic.com` now that HTTPS is enforced.

## 1.0.0 (frozen 18 Nov 2026)
- Release: https://github.com/AlexVerboo/treebot/releases/tag/v1.0.0
