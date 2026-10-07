-- migrate:up

-- The commission percent a trip was created with. Editing the trip's amount recomputes
-- the commission from this percent, so a later change to the driver's percent does not
-- rewrite past trips. NULL: the commission was entered by hand (also all older trips).
ALTER TABLE trips ADD COLUMN commission_pct numeric(5, 2)
    CONSTRAINT trips_commission_pct_check CHECK (commission_pct >= 0 AND commission_pct < 100);

-- migrate:down

ALTER TABLE trips DROP COLUMN commission_pct;
