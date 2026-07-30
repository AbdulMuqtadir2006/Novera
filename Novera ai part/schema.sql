PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS reference_ranges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organ TEXT NOT NULL CHECK (organ IN ('KIDNEY', 'STOMACH', 'ORAL')),
    biomarker TEXT NOT NULL CHECK (biomarker IN ('ph', 'urea_mg_dl', 'creatinine_umol_l', 'temperature_c')),
    min_value REAL NOT NULL,
    max_value REAL NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    UNIQUE (organ, biomarker),
    CHECK (max_value > min_value)
);

CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL UNIQUE,
    ph REAL NOT NULL,
    urea_mg_dl REAL NOT NULL,
    creatinine_umol_l REAL NOT NULL,
    temperature_c REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'NEW' CHECK (status IN ('NEW', 'PROCESSING', 'COMPLETED', 'RETEST_REQUIRED', 'ERROR')),
    ai_prediction TEXT,
    ai_confidence REAL,
    ai_reason TEXT,
    human_confirmation TEXT CHECK (human_confirmation IS NULL OR human_confirmation IN ('KIDNEY', 'STOMACH', 'ORAL')),
    prediction_correct INTEGER CHECK (prediction_correct IS NULL OR prediction_correct IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS confirmed_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reading_id INTEGER NOT NULL UNIQUE,
    organ TEXT NOT NULL CHECK (organ IN ('KIDNEY', 'STOMACH', 'ORAL')),
    notes TEXT,
    confirmed_by TEXT,
    confirmed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (reading_id) REFERENCES readings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS decision_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reading_id INTEGER NOT NULL,
    selected_model TEXT,
    llm_used INTEGER NOT NULL DEFAULT 0 CHECK (llm_used IN (0, 1)),
    specialist_results_json TEXT NOT NULL,
    llm_result_json TEXT,
    final_prediction TEXT NOT NULL,
    final_confidence REAL,
    final_reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (reading_id) REFERENCES readings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_readings_status_created
ON readings (status, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_confirmed_cases_organ_confirmed
ON confirmed_cases (organ, confirmed_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_decision_audit_reading
ON decision_audit (reading_id, created_at DESC);
