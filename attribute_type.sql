CREATE TABLE attribute_type(
_id INTEGER NOT NULL,
id VARCHAR(64) NOT NULL,
name VARCHAR(64) NOT NULL,
columnLabel VARCHAR(64) NOT NULL,
source VARCHAR(128),
target VARCHAR(128) NOT NULL,
type VARCHAR(128) NOT NULL,
converterClass VARCHAR(128) NOT NULL,
props_json TEXT,
PRIMARY KEY(_id)
);
