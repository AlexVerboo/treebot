-- 002_night_awards: TreeBot v2.0 Phase 3.
-- One row per game night whose "Night awards" were posted to GroupMe.
-- The row is the lock: awards.py inserts it first (ON CONFLICT DO NOTHING) and only the run
-- that inserted it posts, so a late or repeated run never posts the same night twice.

CREATE TABLE night_awards (
    night_date  date PRIMARY KEY,               -- Mexico City evening the session started
    games       integer NOT NULL,               -- group games that night
    payload     jsonb NOT NULL,                 -- winners and their numbers
    message     text NOT NULL,                  -- exactly what was posted
    posted_at   timestamptz NOT NULL DEFAULT now()
);

-- The player page groups matches by Mexico City day and by map / mode.
CREATE INDEX matches_map_mode ON matches (map_name, mode);
