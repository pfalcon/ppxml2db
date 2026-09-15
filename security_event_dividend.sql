CREATE TABLE security_event_dividend(
_id INTEGER NOT NULL PRIMARY KEY,
security VARCHAR(36) NOT NULL REFERENCES security(uuid),
date VARCHAR(36) NOT NULL,
type VARCHAR(32) NOT NULL,
source VARCHAR(255),
paymentDate VARCHAR(36),
amount BIGINT,
currency VARCHAR(16),
_order INT NOT NULL
);
CREATE INDEX security_event_dividend__security ON security_event_dividend(security);
