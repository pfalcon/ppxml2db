CREATE TABLE taxonomy_assignment(
-- redundant from DB normal form point of view, but helpful for actual
-- operations on particilar item and taxonomy.
taxonomy VARCHAR(36) NOT NULL REFERENCES taxonomy(uuid),
category VARCHAR(36) NOT NULL REFERENCES taxonomy_category(uuid),
item_type VARCHAR(32) NOT NULL,
-- Can refer to different things, e.g. security, account, etc., so we don't
--- use referential integrity at the DB level.
item VARCHAR(36) NOT NULL,
weight INT NOT NULL DEFAULT 10000,
rank INT NOT NULL DEFAULT 0
);
CREATE INDEX taxonomy_assignment__item_type_item ON taxonomy_assignment(item_type, item);
