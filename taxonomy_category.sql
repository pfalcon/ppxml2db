CREATE TABLE taxonomy_category(
_id INTEGER NOT NULL PRIMARY KEY,
uuid VARCHAR(36) NOT NULL UNIQUE,
taxonomy VARCHAR(36) NOT NULL REFERENCES taxonomy(uuid),
parent VARCHAR(36) REFERENCES taxonomy_category(uuid),
name VARCHAR(100) NOT NULL,
color VARCHAR(100) NOT NULL,
weight INT NOT NULL,
rank INT NOT NULL
);

CREATE UNIQUE INDEX taxonomy_category__uuid ON taxonomy_category(uuid);
