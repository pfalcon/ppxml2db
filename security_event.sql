CREATE TABLE security_event(
security VARCHAR(36) NOT NULL REFERENCES security(uuid),
date VARCHAR(36) NOT NULL,
type VARCHAR(32) NOT NULL,
details TEXT
);
