CREATE TABLE account(
uuid VARCHAR(36) NOT NULL,
type VARCHAR(10) NOT NULL,
name VARCHAR(128),
referenceAccount VARCHAR(36) REFERENCES account(uuid),
currencyCode VARCHAR(16),
isRetired INT NOT NULL DEFAULT 0,
updatedAt VARCHAR(64) NOT NULL,
PRIMARY KEY(uuid)
);
#CREATE UNIQUE INDEX account__uuid ON account(uuid);
