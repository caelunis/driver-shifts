-- migrate:up

-- A shift is the driver's working period; every trip belongs to one.
-- A shift that crosses midnight stays one shift, and the "day" of its trips is
-- the local day the shift started on.

CREATE EXTENSION IF NOT EXISTS btree_gist;  -- for the no-overlap EXCLUDE below

CREATE TABLE shifts (
    id               bigserial PRIMARY KEY,
    driver_id        bigint NOT NULL REFERENCES drivers (user_id) ON DELETE CASCADE,
    started_at       timestamptz NOT NULL,
    ended_at         timestamptz,                      -- NULL while the shift is open
    start_offset_min smallint NOT NULL,                -- offsets as sent by the client,
    end_offset_min   smallint,                         -- see the note on trips
    local_day        date NOT NULL,                    -- local day of the start
    note             text NOT NULL DEFAULT '',
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT shifts_end_after_start CHECK (ended_at > started_at),
    CONSTRAINT shifts_max_24h CHECK (ended_at <= started_at + interval '24 hours'),
    CONSTRAINT shifts_end_offset_with_end CHECK ((ended_at IS NULL) = (end_offset_min IS NULL)),
    CONSTRAINT shifts_note_length CHECK (length(note) <= 500),
    -- Lets trips reference (shift, driver) together, see trips_shift_fkey
    CONSTRAINT shifts_id_driver_key UNIQUE (id, driver_id),
    -- A driver cannot be on two shifts at once; an open shift extends to infinity
    CONSTRAINT shifts_no_overlap EXCLUDE USING gist (
        driver_id WITH =,
        tstzrange(started_at, coalesce(ended_at, 'infinity'), '[)') WITH &&
    )
);
-- At most one open shift per driver
CREATE UNIQUE INDEX shifts_one_open_per_driver ON shifts (driver_id) WHERE ended_at IS NULL;
CREATE INDEX shifts_driver_day_idx ON shifts (driver_id, local_day, started_at);

ALTER TABLE trips ADD COLUMN shift_id bigint;

-- Existing trips: one closed shift per driver and local day, from the first trip's
-- start to the last trip's end
INSERT INTO shifts (driver_id, started_at, ended_at, start_offset_min, end_offset_min, local_day)
SELECT driver_id,
       min(start_at),
       max(end_at),
       (array_agg(start_offset_min ORDER BY start_at))[1],
       (array_agg(end_offset_min ORDER BY end_at DESC))[1],
       local_day
FROM trips
GROUP BY driver_id, local_day;

UPDATE trips t SET shift_id = s.id
FROM shifts s
WHERE s.driver_id = t.driver_id AND s.local_day = t.local_day;

ALTER TABLE trips ALTER COLUMN shift_id SET NOT NULL;
-- Composite key: a trip can only belong to a shift of the same driver
ALTER TABLE trips ADD CONSTRAINT trips_shift_fkey
    FOREIGN KEY (shift_id, driver_id) REFERENCES shifts (id, driver_id) ON DELETE CASCADE;

-- The day now comes from the shift; the trip's own local day is redundant
DROP INDEX trips_driver_day_idx;
ALTER TABLE trips DROP COLUMN local_day;
CREATE INDEX trips_shift_idx ON trips (shift_id, start_at);

-- migrate:down

ALTER TABLE trips ADD COLUMN local_day date;
UPDATE trips SET local_day = ((start_at AT TIME ZONE 'UTC') + make_interval(mins => start_offset_min))::date;
ALTER TABLE trips ALTER COLUMN local_day SET NOT NULL;
CREATE INDEX trips_driver_day_idx ON trips (driver_id, local_day, start_at);

DROP INDEX trips_shift_idx;
ALTER TABLE trips DROP CONSTRAINT trips_shift_fkey;
ALTER TABLE trips DROP COLUMN shift_id;
DROP TABLE shifts;
DROP EXTENSION IF EXISTS btree_gist;
