CREATE TABLE taxonomy(
uuid VARCHAR(36) NOT NULL,
name VARCHAR(100) NOT NULL,
root VARCHAR(36) NOT NULL REFERENCES taxonomy_category(uuid),
PRIMARY KEY(uuid)
);
