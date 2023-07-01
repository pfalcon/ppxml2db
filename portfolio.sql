CREATE TABLE portfolio(
uuid VARCHAR(36) NOT NULL,
name VARCHAR(128),
referenceAccount VARCHAR(36) NOT NULL REFERENCES account(uuid),
isRetired INT NOT NULL DEFAULT 0,
updatedAt VARCHAR(64) NOT NULL,
PRIMARY KEY(uuid)
);
#CREATE UNIQUE INDEX portfolio__uuid ON portfolio(uuid);
