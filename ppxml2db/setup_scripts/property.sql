CREATE TABLE property(
name VARCHAR(64) NOT NULL,
special INT NOT NULL DEFAULT 0,
value VARCHAR(256) NOT NULL
);
CREATE UNIQUE INDEX property__name ON property(name);
