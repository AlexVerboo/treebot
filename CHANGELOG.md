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

### Phase 2 — Postgres on Neon
- **Match history in PostgreSQL (Neon).** New tables: `players`, `matches`, `match_teams`, `match_players` (one row per member per match: K/D/A, damage, accuracy, score, medals and per-mode stats in JSONB), `stats_snapshots`, `coach_cache` (for Phase 4) and `ingest_runs`. Only Trees in Space members are stored.
- **`db.py`:** psycopg 3 with a connection pool that keeps no idle connections (so Neon can suspend), `sslmode=require` forced, prepared statements off for Neon's pooler.
- **Versioned migrations** in `migrations/` and an idempotent `migrate.py` (transaction + advisory lock per file, checksum check). Workflows run it before touching the database.
- **Idempotent ingestion** (`ingest.py`): the match history tells which (match, member) rows are missing; only those matches are requested from Halo, and everything is saved with `ON CONFLICT DO NOTHING`. Runs in the daily job, at 22:47 and 01:47 Mexico City (new **Ingest matches** workflow) and on every `ggs`.
- **Easy new members:** **Add member** also backfills their history (90 days by default), and anyone new or returning in the members sheet gets 30 days automatically. Removed members keep their history (`active = false`).
- **One-time import** from the "XUIDs" and "Player Stats" sheets (`import_sheets.py`) and a manual **Database** workflow (`status`, `migrate`, `import-sheets`, `backfill`; Neon branch `dev` or `production`).
- **`ggs` reads from the database** and only asks Halo for what is missing. Same message as before. If the database fails it alerts and builds the recap straight from Halo.
- **Daily stats snapshots** in `stats_snapshots`; the "Player Stats" sheet is still written first and stays the readable view.
- **`/health?deep=1`** now also checks the database (short timeout, runs next to the Sheets check, never takes the endpoint down) and shows the last ingestion.
- **Tests:** 55 `pytest` tests; CI starts a throwaway Postgres 16 for the database tests.

## 1.0.0 (frozen 18 Nov 2026)
- Release: https://github.com/AlexVerboo/treebot/releases/tag/v1.0.0
