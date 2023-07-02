CREATE TABLE xact_cross_entry(
type VARCHAR(12) NOT NULL,
portfolio VARCHAR(36) NOT NULL REFERENCES account(uuid),
portfolio_xact VARCHAR(36) NOT NULL REFERENCES xact(uuid),
account VARCHAR(36) NOT NULL REFERENCES account(uuid),
account_xact VARCHAR(36) NOT NULL REFERENCES xact(uuid)
);
CREATE INDEX xact_cross_entry__portfolio_xact ON xact_cross_entry(portfolio_xact);
CREATE INDEX xact_cross_entry__account_xact ON xact_cross_entry(account_xact);
