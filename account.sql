CREATE TABLE account(
uuid VARCHAR(36) NOT NULL,
type VARCHAR(10) NOT NULL,
name VARCHAR(128),
referenceAccount VARCHAR(36) REFERENCES account(uuid),
currency VARCHAR(16),
note TEXT,
isRetired INT NOT NULL DEFAULT 0,
updatedAt VARCHAR(64) NOT NULL,
_xmlid INT NOT NULL,
_order INT NOT NULL,
PRIMARY KEY(uuid)
);
