CREATE TABLE config_entry(
config_set INT NOT NULL REFERENCES config_set(_id),
uuid VARCHAR(36),
name VARCHAR(64),
data TEXT
);
