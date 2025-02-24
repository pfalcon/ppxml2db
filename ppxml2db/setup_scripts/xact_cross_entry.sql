CREATE TABLE xact_cross_entry(
type VARCHAR(32) NOT NULL,
from_acc VARCHAR(36) REFERENCES account(uuid),
from_xact VARCHAR(36) REFERENCES xact(uuid),
to_acc VARCHAR(36) NOT NULL REFERENCES account(uuid),
to_xact VARCHAR(36) NOT NULL REFERENCES xact(uuid)
);
CREATE INDEX xact_cross_entry__from_xact ON xact_cross_entry(from_xact);
CREATE INDEX xact_cross_entry__to_xact ON xact_cross_entry(to_xact);
