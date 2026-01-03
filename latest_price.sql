CREATE TABLE latest_price(
security VARCHAR(36) NOT NULL REFERENCES security(uuid),
tstamp VARCHAR(32) NOT NULL,
value BIGINT NOT NULL,
high BIGINT,
low BIGINT,
volume BIGINT
);
CREATE UNIQUE INDEX latest_price__security ON latest_price(security);
