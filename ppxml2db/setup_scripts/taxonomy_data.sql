CREATE TABLE taxonomy_data(
taxonomy VARCHAR(36) NOT NULL REFERENCES taxonomy(uuid),
-- Can be NULL for taxonomy-level data
category VARCHAR(36) REFERENCES taxonomy_category(uuid),
name VARCHAR(64) NOT NULL,
value VARCHAR(256) NOT NULL
);
CREATE INDEX taxonomy_data__taxonomy ON taxonomy_data(taxonomy);
CREATE INDEX taxonomy_data__category ON taxonomy_data(category);
