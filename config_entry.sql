CREATE TABLE config_entry(
config_set INT NOT NULL REFERENCES config_set(_id),
uuid VARCHAR(36) NOT NULL,
name VARCHAR(64) NOT NULL,
data TEXT,
PRIMARY KEY(uuid)
);
