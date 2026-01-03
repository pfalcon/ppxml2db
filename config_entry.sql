CREATE TABLE config_entry(
config_set INT NOT NULL REFERENCES config_set(_id),
uuid VARCHAR(255), -- not really a uuid, more like id
name VARCHAR(255),
data TEXT
);
