CREATE TABLE dashboard(
_id INTEGER NOT NULL,
name VARCHAR(64) NOT NULL,
config_json TEXT NOT NULL,
columns_json TEXT NOT NULL,
PRIMARY KEY(_id)
);
