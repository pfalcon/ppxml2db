CREATE TABLE security(
uuid VARCHAR(36) NOT NULL,
onlineId VARCHAR(64),
name VARCHAR(128),
-- Yes, can be absent (dax.xml).
currencyCode VARCHAR(16),
note TEXT,
isin VARCHAR(16),
tickerSymbol VARCHAR(32),
wkn VARCHAR(32),
feedTickerSymbol VARCHAR(32),
feed VARCHAR(32),
isRetired INT NOT NULL DEFAULT 0,
updatedAt VARCHAR(64) NOT NULL,
PRIMARY KEY(uuid)
);
