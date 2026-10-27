CREATE TABLE IF NOT EXISTS syncs (
    id          TEXT    PRIMARY KEY,
    secret_hash TEXT    NOT NULL,
    blob        TEXT    NOT NULL,
    updated     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_syncs_updated ON syncs (updated);

CREATE TABLE IF NOT EXISTS usage (
    day    TEXT    PRIMARY KEY,
    writes INTEGER NOT NULL
);
