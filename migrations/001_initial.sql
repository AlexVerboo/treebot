-- 001_initial: TreeBot v2.0 Phase 2 schema.
-- Applied by migrate.py inside one transaction. Never edit an applied migration:
-- add a new numbered file instead (migrate.py checks the checksum).

-- Members. Google Sheets ("Trees in Space Members") stays the source of truth;
-- every ingestion syncs this table from it. Ex-members keep their history with active = false.
CREATE TABLE players (
    xuid        bigint PRIMARY KEY,
    gamertag    text NOT NULL,
    active      boolean NOT NULL DEFAULT true,
    first_seen  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX players_gamertag_active ON players (lower(gamertag)) WHERE active;

-- One row per match that at least one member played.
CREATE TABLE matches (
    match_id        uuid PRIMARY KEY,
    start_time      timestamptz NOT NULL,
    end_time        timestamptz,
    duration_s      integer,
    map_asset_id    uuid,
    map_version_id  uuid,
    map_name        text,          -- cleaned: 'Breaker', not 'Breaker One Flag CTF'
    mode            text,          -- display name, same as the GGs recap: 'Capture the Flag'
    mode_category   text,          -- raw API enum name: 'CTF', 'SLAYER'...
    playlist_id     uuid,          -- NULL in custom games
    playlist_name   text,
    lifecycle       text,          -- 'matchmade' | 'custom' | 'local_area_network'
    is_ranked       boolean NOT NULL DEFAULT false,
    season_id       text,
    ingested_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX matches_start_time ON matches (start_time DESC);

-- Result per team (the "50-43" and who won).
CREATE TABLE match_teams (
    match_id  uuid NOT NULL REFERENCES matches ON DELETE CASCADE,
    team_id   smallint NOT NULL,
    outcome   text,                -- 'win' | 'loss' | 'tie' | 'did_not_finish'
    rank      smallint,
    score     integer,
    PRIMARY KEY (match_id, team_id)
);

-- One row per member per match (only Trees in Space members are stored).
CREATE TABLE match_players (
    match_id              uuid NOT NULL REFERENCES matches ON DELETE CASCADE,
    xuid                  bigint NOT NULL REFERENCES players,
    start_time            timestamptz NOT NULL,   -- copy of matches.start_time for the index below
    team_id               smallint,
    outcome               text,
    rank                  smallint,
    kills                 integer,
    deaths                integer,
    assists               integer,
    damage_dealt          integer,
    damage_taken          integer,
    shots_fired           integer,
    shots_hit             integer,
    accuracy              numeric(5, 2),
    score                 integer,
    personal_score        integer,
    headshot_kills        integer,
    melee_kills           integer,
    grenade_kills         integer,
    power_weapon_kills    integer,
    callout_assists       integer,
    max_killing_spree     integer,
    driver_assists        integer,
    vehicle_destroys      integer,
    hijacks               integer,
    time_played_s         integer,
    joined_in_progress    boolean,
    present_at_completion boolean,
    mode_stats            jsonb,   -- per-mode numbers: flag caps, zone time, skull time...
    medals                jsonb,   -- {"<medal name_id>": count}
    PRIMARY KEY (match_id, xuid)
);
CREATE INDEX match_players_xuid_time ON match_players (xuid, start_time DESC);

-- Daily photo of each member's service record ("Player Stats" history).
CREATE TABLE stats_snapshots (
    xuid           bigint NOT NULL REFERENCES players,
    snapshot_date  date NOT NULL,              -- Mexico City day
    season         text NOT NULL DEFAULT '',   -- '' = lifetime, otherwise STATS_SEASON
    matches        integer,
    wins           integer,
    losses         integer,
    kills          integer,
    deaths         integer,
    assists        integer,
    damage_dealt   bigint,
    damage_taken   bigint,
    accuracy       numeric(5, 2),
    time_played_s  bigint,
    row            jsonb,                      -- the exact "Player Stats" row (roles.STATS keys)
    record         jsonb,                      -- compact overall service record
    taken_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (xuid, snapshot_date, season)
);

-- Phase 4 (coach!): one answer per player per day, plus token usage.
CREATE TABLE coach_cache (
    xuid           bigint NOT NULL REFERENCES players,
    cache_date     date NOT NULL,
    input          jsonb NOT NULL,             -- numbers computed in Python
    response       text NOT NULL,
    model          text,
    input_tokens   integer,
    output_tokens  integer,
    created_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (xuid, cache_date)
);

-- One row per ingestion run (shown in /health?deep=1).
CREATE TABLE ingest_runs (
    id           bigserial PRIMARY KEY,
    source       text NOT NULL,                -- 'daily' | 'night' | 'ggs' | 'backfill' | 'manual'
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    new_matches  integer NOT NULL DEFAULT 0,
    new_rows     integer NOT NULL DEFAULT 0,
    errors       integer NOT NULL DEFAULT 0,
    status       text NOT NULL DEFAULT 'running'  -- 'running' | 'ok' | 'partial' | 'failed'
);
