CREATE TABLE property(
name VARCHAR(64) NOT NULL,
value VARCHAR(256) NOT NULL
);
CREATE UNIQUE INDEX property__name ON property(name);
