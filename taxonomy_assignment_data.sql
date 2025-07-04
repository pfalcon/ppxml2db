CREATE TABLE taxonomy_assignment_data(
assignment INT NOT NULL REFERENCES taxonomy_assignment(_id),
name VARCHAR(64) NOT NULL,
type VARCHAR(64) NOT NULL,
value VARCHAR(256) NOT NULL
);
