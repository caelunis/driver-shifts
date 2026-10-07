-- migrate:up

-- Trips: sane bounds, and a driver cannot be on two trips at once
ALTER TABLE trips
    ADD CONSTRAINT trips_amount_max CHECK (amount <= 500000),
    ADD CONSTRAINT trips_duration CHECK (end_at - start_at BETWEEN interval '1 minute' AND interval '6 hours'),
    ADD CONSTRAINT trips_no_overlap EXCLUDE USING gist (
        driver_id WITH =,
        tstzrange(start_at, end_at, '[)') WITH &&
    );

-- Timezone: an IANA name instead of a fixed offset. Offsets that map to one obvious zone
-- get it; other whole-hour offsets become Etc/GMT zones (whose sign is inverted:
-- Etc/GMT-5 is UTC+5).
ALTER TABLE drivers ALTER COLUMN default_tz DROP DEFAULT;
UPDATE drivers SET default_tz = CASE default_tz
    WHEN '+05:00' THEN 'Asia/Almaty'
    WHEN '+00:00' THEN 'UTC'
    WHEN '+05:30' THEN 'Asia/Kolkata'
    WHEN '+05:45' THEN 'Asia/Kathmandu'
    WHEN '+04:30' THEN 'Asia/Kabul'
    WHEN '+03:30' THEN 'Asia/Tehran'
    WHEN '+06:30' THEN 'Asia/Yangon'
    WHEN '+09:30' THEN 'Australia/Darwin'
    WHEN '-03:30' THEN 'America/St_Johns'
    ELSE CASE WHEN substr(default_tz, 5, 2) = '00'
              THEN 'Etc/GMT' || CASE WHEN left(default_tz, 1) = '+' THEN '-' ELSE '+' END
                             || substr(default_tz, 2, 2)::int
              ELSE 'UTC' END
END;
ALTER TABLE drivers ALTER COLUMN default_tz SET DEFAULT 'Asia/Almaty';

-- Car: model and plate apart; the plate is unique among drivers. A plate written at the
-- end of the old free-text field ("Hyundai Accent, 777 AAA 02") is moved over.
ALTER TABLE drivers RENAME COLUMN car TO car_model;
ALTER TABLE drivers ADD COLUMN car_plate text
    CONSTRAINT drivers_car_plate_format CHECK (car_plate ~ '^\d{3}[A-Z]{2,3}(0[1-9]|1\d|20)$');
WITH parsed AS (
    SELECT user_id,
           regexp_match(car_model, '^(.*?)[\s,]*(\d{3})\s*([A-Z]{2,3})\s*(0[1-9]|1\d|20)$') AS m
    FROM drivers
), plates AS (
    -- If several drivers typed the same plate, the earliest account keeps it
    SELECT DISTINCT ON (m[2] || m[3] || m[4]) user_id, m[1] AS model, m[2] || m[3] || m[4] AS plate
    FROM parsed WHERE m IS NOT NULL
    ORDER BY m[2] || m[3] || m[4], user_id
)
UPDATE drivers d SET car_model = p.model, car_plate = p.plate
FROM plates p WHERE p.user_id = d.user_id;
CREATE UNIQUE INDEX drivers_car_plate_key ON drivers (car_plate);

-- migrate:down

DROP INDEX drivers_car_plate_key;
UPDATE drivers SET car_model = concat_ws(', ', nullif(car_model, ''), car_plate);
ALTER TABLE drivers DROP COLUMN car_plate;
ALTER TABLE drivers RENAME COLUMN car_model TO car;

ALTER TABLE drivers ALTER COLUMN default_tz DROP DEFAULT;
UPDATE drivers d SET default_tz =
    CASE WHEN m < 0 THEN '-' ELSE '+' END
    || lpad((abs(m) / 60)::text, 2, '0') || ':' || lpad((abs(m) % 60)::text, 2, '0')
FROM (SELECT name, (extract(epoch FROM utc_offset) / 60)::int AS m FROM pg_timezone_names) z
WHERE z.name = d.default_tz;
ALTER TABLE drivers ALTER COLUMN default_tz SET DEFAULT '+05:00';

ALTER TABLE trips
    DROP CONSTRAINT trips_no_overlap,
    DROP CONSTRAINT trips_duration,
    DROP CONSTRAINT trips_amount_max;
