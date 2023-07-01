CREATE TABLE account(
uuid VARCHAR(36) NOT NULL,
name VARCHAR(128),
currencyCode VARCHAR(16) NOT NULL,
isRetired INT NOT NULL DEFAULT 0,
updatedAt VARCHAR(64) NOT NULL,
PRIMARY KEY(uuid)
);
#CREATE UNIQUE INDEX account__uuid ON account(uuid);
