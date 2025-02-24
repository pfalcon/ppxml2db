CREATE TABLE security_prop(
security VARCHAR(36) NOT NULL REFERENCES security(uuid),
type VARCHAR(32) NOT NULL,
name VARCHAR(36) NOT NULL,
value TEXT,
seq INT NOT NULL DEFAULT 0
);
CREATE INDEX security_prop__security ON security_prop(security);
