-- migrations/001_init.sql
-- Инициализация БД для AI Landing Page Uniqueizer (SQLite 3.x)
-- Production-ready конфигурация для работы в Docker-контейнере.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;          -- Баланс durability/производительность для WAL
PRAGMA temp_store = MEMORY;
PRAGMA busy_timeout = 5000;           -- 5s ожидание блокировки

----------------------------------------------------------------------
-- TABLE: jobs
-- Хранит жизненный цикл фоновых задач (pipeline state machine)
----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_url TEXT NOT NULL,               -- Исходный URL лендинга
    status TEXT NOT NULL DEFAULT 'pending', -- pending | running | done | failed
    metadata TEXT,                          -- JSON-строка с произвольными данными (nullable)
    error_message TEXT,                     -- Текст ошибки при status='failed'
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    CHECK (status IN ('pending','running','done','failed'))
);

-- Индекс для быстрого выбора следующей pending-задачи
CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at
    ON jobs (status, created_at);

-- Индекс для мониторинга и TTL-очистки
CREATE INDEX IF NOT EXISTS idx_jobs_updated_at
    ON jobs (updated_at);

----------------------------------------------------------------------
-- TABLE: artifacts
-- Хранит метаданные финального ZIP-архива
-- 1:1 связь с jobs
----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL UNIQUE,
    path TEXT NOT NULL,              -- Абсолютный или относительный путь к ZIP
    size INTEGER NOT NULL,           -- Размер файла в байтах
    hash TEXT NOT NULL,              -- SHA-256 архива
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (job_id)
        REFERENCES jobs(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_artifacts_job_id
    ON artifacts (job_id);

----------------------------------------------------------------------
-- TABLE: settings
-- Глобальные настройки приложения (key-value)
----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
);

----------------------------------------------------------------------
-- TABLE: logs
-- Высоконагруженная таблица логов (pipeline markers + runtime logs)
----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',  -- info | warn | error
    message TEXT NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT (datetime('now')),
    CHECK (level IN ('info','warn','error')),
    FOREIGN KEY (job_id)
        REFERENCES jobs(id)
        ON DELETE CASCADE
);

-- Критичный индекс для:
-- 1) стриминга логов по job_id
-- 2) расчёта progress_pct по маркерам
CREATE INDEX IF NOT EXISTS idx_logs_job_id_timestamp
    ON logs (job_id, timestamp);

----------------------------------------------------------------------
-- TRIGGERS: автоматическое обновление updated_at
----------------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS trg_jobs_updated_at
AFTER UPDATE ON jobs
FOR EACH ROW
BEGIN
    UPDATE jobs
    SET updated_at = datetime('now')
    WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_settings_updated_at
AFTER UPDATE ON settings
FOR EACH ROW
BEGIN
    UPDATE settings
    SET updated_at = datetime('now')
    WHERE key = NEW.key;
END;

----------------------------------------------------------------------
-- INITIAL SETTINGS (idempotent)
----------------------------------------------------------------------

INSERT OR IGNORE INTO settings (key, value) VALUES
    ('openai_api_key', ''),
    ('anthropic_api_key', ''),
    ('ai_provider', 'openai'),
    ('openai_model', 'gpt-4o-mini'),
    ('anthropic_model', 'claude-3-haiku-20240307'),
    ('noise_intensity', '0.01'),
    ('js_class_exclusion_prefixes', 'js-,swiper-');