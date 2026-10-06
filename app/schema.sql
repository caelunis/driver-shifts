CREATE TABLE IF NOT EXISTS drivers (
    id                     bigserial PRIMARY KEY,
    email                  text NOT NULL,
    password_hash          text NOT NULL,
    name                   text NOT NULL DEFAULT '',
    car                    text NOT NULL DEFAULT '',
    default_tz             text NOT NULL DEFAULT '+05:00',
    default_commission_pct numeric(5, 2),
    created_at             timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS drivers_email_key ON drivers (lower(email));
-- Added after the first release: ALTER keeps existing databases working
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'driver'
    CHECK (role IN ('driver', 'admin'));

CREATE TABLE IF NOT EXISTS sessions (
    token_hash text PRIMARY KEY,
    driver_id  bigint NOT NULL REFERENCES drivers (id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_driver_idx ON sessions (driver_id);

-- timestamptz stores an instant and drops the original offset, so the offset
-- is kept separately: it decides which local day a trip belongs to and is
-- needed to return times exactly as the client sent them.
CREATE TABLE IF NOT EXISTS trips (
    driver_id        bigint NOT NULL REFERENCES drivers (id) ON DELETE CASCADE,
    id               text NOT NULL,
    start_at         timestamptz NOT NULL,
    end_at           timestamptz NOT NULL,
    start_offset_min smallint NOT NULL,
    end_offset_min   smallint NOT NULL,
    local_day        date NOT NULL,
    amount           integer NOT NULL CHECK (amount > 0),
    payment          text NOT NULL CHECK (payment IN ('cash', 'card')),
    commission       integer NOT NULL CHECK (commission >= 0 AND commission <= amount),
    CHECK (end_at > start_at),
    -- Duplicate protection is enforced by the database, per driver
    PRIMARY KEY (driver_id, id)
);
CREATE INDEX IF NOT EXISTS trips_driver_day_idx ON trips (driver_id, local_day, start_at);
