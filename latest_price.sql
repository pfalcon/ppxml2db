CREATE TABLE latest_price(
security VARCHAR(36) NOT NULL REFERENCES security(uuid),
tstamp VARCHAR(32) NOT NULL,
value INT NOT NULL,
high INT,
low INT,
volume INT
);
CREATE UNIQUE INDEX latest_price__security ON latest_price(security);
