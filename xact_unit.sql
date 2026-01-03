CREATE TABLE xact_unit(
xact VARCHAR(36) NOT NULL REFERENCES xact(uuid),
type VARCHAR(16) NOT NULL,
amount BIGINT NOT NULL,
currency VARCHAR(16) NOT NULL,
forex_amount BIGINT,
forex_currency VARCHAR(16),
-- In PP, exchangeRate is arbitrary-precision float, so we store it as a
-- string (actually, Sqlite is known to ignore the column type and use
-- "duck typing" for values, i.e. it may convert string looking like float
-- into (limited-precision) float, so if any issues are seen, we may need
-- to add more guards).
exchangeRate VARCHAR(16)
);
CREATE INDEX xact_unit__xact ON xact_unit(xact);
