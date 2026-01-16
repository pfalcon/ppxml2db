CREATE TABLE taxonomy(
_id INTEGER NOT NULL PRIMARY KEY,
uuid VARCHAR(36) NOT NULL UNIQUE,
name VARCHAR(100) NOT NULL,
root VARCHAR(36) NOT NULL -- REFERENCES taxonomy_category(uuid), -- commented out to avoid circular dependency
);

CREATE UNIQUE INDEX taxonomy__uuid ON taxonomy(uuid);
