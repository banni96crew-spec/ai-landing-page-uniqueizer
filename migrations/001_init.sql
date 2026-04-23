PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    target_url    TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at
    ON jobs (status, created_at);

CREATE TABLE IF NOT EXISTS artifacts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER NOT NULL REFERENCES jobs(id),
    file_path  TEXT    NOT NULL,
    file_size  INTEGER,
    hash       TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT    NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO settings (key, value) VALUES
    ('openai_api_key',              ''),
    ('anthropic_api_key',           ''),
    ('ai_provider',                 'openai'),
    ('openai_model',                'gpt-4o-mini'),
    ('anthropic_model',             'claude-3-haiku-20240307'),
    ('noise_intensity',             '0.01'),
    ('js_class_exclusion_prefixes', 'js-,swiper-');

CREATE TABLE IF NOT EXISTS logs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id    INTEGER NOT NULL REFERENCES jobs(id),
    level     TEXT    NOT NULL DEFAULT 'info',
    message   TEXT    NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_logs_job_id_timestamp
    ON logs (job_id, timestamp);

CREATE TRIGGER IF NOT EXISTS trg_jobs_updated_at
AFTER UPDATE ON jobs
BEGIN
    UPDATE jobs SET updated_at = datetime('now') WHERE id = NEW.id;
END;
