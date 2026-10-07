-- migrate:up

-- Accounts: who can log in. An admin is a user without a driver profile.
CREATE TABLE users (
    id            bigserial PRIMARY KEY,
    email         text NOT NULL,
    password_hash text NOT NULL,
    role          text NOT NULL DEFAULT 'driver'
        CONSTRAINT users_role_check CHECK (role IN ('driver', 'admin')),
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_email_key ON users (lower(email));

-- Driver profile, 1:1 with a user of role 'driver'
CREATE TABLE drivers (
    user_id                bigint PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    name                   text NOT NULL,
    car                    text NOT NULL DEFAULT '',
    default_tz             text NOT NULL DEFAULT '+05:00',
    default_commission_pct numeric(5, 2),
    CONSTRAINT drivers_commission_pct_check
        CHECK (default_commission_pct >= 0 AND default_commission_pct < 100)
);

-- Only a SHA-256 of the session token is stored
CREATE TABLE sessions (
    token_hash text PRIMARY KEY,
    user_id    bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL
);
CREATE INDEX sessions_user_idx ON sessions (user_id);

-- timestamptz stores an instant and drops the original offset, so the offset is
-- kept separately: it decides which local day a trip belongs to and is needed to
-- return times exactly as the client sent them.
CREATE TABLE trips (
    driver_id        bigint NOT NULL REFERENCES drivers (user_id) ON DELETE CASCADE,
    id               text NOT NULL,
    start_at         timestamptz NOT NULL,
    end_at           timestamptz NOT NULL,
    start_offset_min smallint NOT NULL,
    end_offset_min   smallint NOT NULL,
    local_day        date NOT NULL,
    amount           integer NOT NULL CONSTRAINT trips_amount_check CHECK (amount > 0),
    payment          text NOT NULL CONSTRAINT trips_payment_check CHECK (payment IN ('cash', 'card')),
    commission       integer NOT NULL,
    -- Commission is strictly less than the amount: a trip always leaves the driver something
    CONSTRAINT trips_commission_check CHECK (commission >= 0 AND commission < amount),
    CONSTRAINT trips_end_after_start CHECK (end_at > start_at),
    -- Duplicate protection is enforced by the database, per driver
    PRIMARY KEY (driver_id, id)
);
CREATE INDEX trips_driver_day_idx ON trips (driver_id, local_day, start_at);

-- migrate:down

DROP TABLE trips;
DROP TABLE sessions;
DROP TABLE drivers;
DROP TABLE users;
