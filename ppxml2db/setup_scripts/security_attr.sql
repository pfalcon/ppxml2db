CREATE TABLE security_attr(
security VARCHAR(36) NOT NULL REFERENCES security(uuid),
attr_uuid VARCHAR(36) NOT NULL,
type VARCHAR(32) NOT NULL,
value TEXT,
seq INT NOT NULL DEFAULT 0
);
CREATE INDEX security_attr__security ON security_attr(security);
CREATE UNIQUE INDEX security_attr__security_attr_uuid ON security_attr(security, attr_uuid);
