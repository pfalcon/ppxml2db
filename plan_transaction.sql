CREATE TABLE plan_transaction(
plan INTEGER NOT NULL REFERENCES plan(_id),
xact VARCHAR(36) NOT NULL REFERENCES xact(uuid),
seq INTEGER NOT NULL
);
CREATE INDEX plan_transaction__xact ON plan_transaction(xact);
