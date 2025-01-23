CREATE TABLE security(
uuid VARCHAR(36) NOT NULL,
onlineId VARCHAR(64),
name VARCHAR(128),
-- Yes, can be absent (dax.xml).
currency VARCHAR(16),
note TEXT,
isin VARCHAR(16),
tickerSymbol VARCHAR(32),
calendar VARCHAR(32),
wkn VARCHAR(32),
feedTickerSymbol VARCHAR(32),
feed VARCHAR(32),
feedURL VARCHAR(512),
latestFeed VARCHAR(32),
latestFeedURL VARCHAR(512),
isRetired INT NOT NULL DEFAULT 0,
updatedAt VARCHAR(64) NOT NULL,
PRIMARY KEY(uuid)
);

CREATE INDEX security__tickerSymbol ON security(tickerSymbol);
