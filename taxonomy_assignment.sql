CREATE TABLE taxonomy_assignment(
category VARCHAR(36) NOT NULL REFERENCES taxonomy_category(uuid),
item_type VARCHAR(32) NOT NULL,
-- Can refer to different things, e.g. security, account, etc., so we don't
--- use referential integrity at the DB level.
item VARCHAR(36) NOT NULL,
weight INT NOT NULL,
rank INT NOT NULL
);
CREATE INDEX taxonomy_assignment__item_type_item ON taxonomy_assignment(item_type, item);
