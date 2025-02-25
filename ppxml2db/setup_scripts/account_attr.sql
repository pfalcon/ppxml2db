CREATE TABLE account_attr(
account VARCHAR(36) NOT NULL REFERENCES account(uuid),
attr_uuid VARCHAR(36) NOT NULL,
type VARCHAR(32) NOT NULL,
value TEXT,
seq INT NOT NULL DEFAULT 0
);
