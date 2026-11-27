"""
Applies the SQL migrations in /migrations to the database in DATABASE_URL.

    python migrate.py            # apply what is missing
    python migrate.py --status   # only show what is applied / pending

How it works:
- Files are applied in name order (001_..., 002_...). Each one runs in its own transaction
  and is recorded in schema_migrations, so running this script again does nothing (idempotent).
- Every transaction first takes pg_advisory_xact_lock: if two workflows start at the same time,
  the second waits and then sees the migration already applied. (A session lock would not work
  through Neon's pooler; a transaction lock does.)
- The sha256 of each applied file is stored. If someone edits a migration that was already
  applied, this script stops with an error: create a new numbered file instead.
"""

import hashlib
import os
import sys

import db

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
LOCK_KEY = 7_462_310_001      # any constant; identifies "treebot migrations"

BOOKKEEPING = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     text PRIMARY KEY,
    checksum    text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
)
"""


class MigrationError(RuntimeError):
    pass


def log(msg):
    print(msg, flush=True)


def available(directory=MIGRATIONS_DIR):
    """[(version, sql, checksum)] sorted by file name."""
    out = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".sql"):
            continue
        with open(os.path.join(directory, name), encoding="utf-8") as f:
            sql = f.read()
        out.append((name[:-4], sql, hashlib.sha256(sql.encode()).hexdigest()))
    return out


def _applied(conn):
    return dict(conn.execute("SELECT version, checksum FROM schema_migrations").fetchall())


def apply(conn, directory=MIGRATIONS_DIR):
    """Applies pending migrations with an open connection. Returns the versions applied."""
    conn.autocommit = False
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
        conn.execute(BOOKKEEPING)
    done = []
    for version, sql, checksum in available(directory):
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
            applied = _applied(conn)            # read again under the lock
            if version in applied:
                if applied[version] != checksum:
                    raise MigrationError(
                        f"{version}.sql changed after it was applied. "
                        "Do not edit applied migrations: add a new numbered file.")
                continue
            conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                         (version, checksum))
        log(f"Applied {version}")
        done.append(version)
    return done


def status(conn, directory=MIGRATIONS_DIR):
    conn.execute(BOOKKEEPING)
    applied = _applied(conn)
    return [(v, "applied" if v in applied else "pending") for v, _, _ in available(directory)]


def main(argv):
    if not db.enabled():
        log("DATABASE_URL is not set: nothing to migrate.")
        return 0
    with db.connect_direct() as conn:
        if "--status" in argv:
            for version, state in status(conn):
                log(f"{version}: {state}")
            return 0
        done = apply(conn)
    log(f"Database is up to date ({len(done)} migration(s) applied now).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        log(f"Migration failed: {e!r}")
        import alerts
        alerts.send(f"Database migration failed: {type(e).__name__}: {e}"[:500], key="db-migrate")
        sys.exit(1)
