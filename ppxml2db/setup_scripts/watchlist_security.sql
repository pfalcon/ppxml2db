CREATE TABLE watchlist_security(
list INT NOT NULL REFERENCES watchlist(_id),
security VARCHAR(36) NOT NULL REFERENCES security(uuid)
);
CREATE INDEX watchlist_security__list ON watchlist_security(list);
