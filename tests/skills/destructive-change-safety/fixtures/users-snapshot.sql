-- Recovery point for the users table, used as a snapshot_path fixture.
CREATE TABLE users (id INTEGER PRIMARY KEY, active INTEGER);
INSERT INTO users VALUES (1, 0);
