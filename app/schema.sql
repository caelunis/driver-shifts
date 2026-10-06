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
    commission       integer NOT NULL,
    -- Commission is strictly less than the amount: a trip always leaves the driver something
    CONSTRAINT trips_commission_check CHECK (commission >= 0 AND commission < amount),
    CHECK (end_at > start_at),
    -- Duplicate protection is enforced by the database, per driver
    PRIMARY KEY (driver_id, id)
);
CREATE INDEX IF NOT EXISTS trips_driver_day_idx ON trips (driver_id, local_day, start_at);

-- Databases created before the "commission < amount" rule have the old unnamed
-- "<= amount" check. Replace it; NOT VALID keeps existing rows as they are and
-- enforces the rule for new ones.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint
               WHERE conrelid = 'trips'::regclass AND conname = 'trips_check'
                 AND pg_get_constraintdef(oid) LIKE '%commission <= amount%') THEN
        ALTER TABLE trips DROP CONSTRAINT trips_check;
        ALTER TABLE trips ADD CONSTRAINT trips_commission_check
            CHECK (commission >= 0 AND commission < amount) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'drivers'::regclass AND conname = 'drivers_commission_pct_check') THEN
        ALTER TABLE drivers ADD CONSTRAINT drivers_commission_pct_check
            CHECK (default_commission_pct >= 0 AND default_commission_pct < 100) NOT VALID;
    END IF;
END $$;
