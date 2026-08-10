-- NOVERA — PostgreSQL schema.
-- Idempotent: safe to run repeatedly (CREATE TABLE/INDEX IF NOT EXISTS).

-- ---------------------------------------------------------------------------
-- Screening pipeline (novera.py's deterministic organ-screening core)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS reference_ranges (
    id          SERIAL PRIMARY KEY,
    organ       TEXT NOT NULL CHECK (organ IN ('KIDNEY', 'STOMACH', 'ORAL')),
    biomarker   TEXT NOT NULL CHECK (biomarker IN ('ph', 'urea_mg_dl', 'creatinine_umol_l', 'temperature_c')),
    min_value   DOUBLE PRECISION NOT NULL,
    max_value   DOUBLE PRECISION NOT NULL,
    weight      DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    UNIQUE (organ, biomarker),
    CHECK (max_value > min_value)
);

CREATE TABLE IF NOT EXISTS screening_cases (
    id                  SERIAL PRIMARY KEY,
    case_id             TEXT NOT NULL UNIQUE,
    ph                  DOUBLE PRECISION NOT NULL,
    urea_mg_dl          DOUBLE PRECISION NOT NULL,
    creatinine_umol_l   DOUBLE PRECISION NOT NULL,
    temperature_c       DOUBLE PRECISION NOT NULL,
    status              TEXT NOT NULL DEFAULT 'NEW'
                        CHECK (status IN ('NEW', 'PROCESSING', 'COMPLETED', 'RETEST_REQUIRED', 'ERROR')),
    ai_prediction       TEXT CHECK (ai_prediction IS NULL OR ai_prediction IN ('KIDNEY', 'STOMACH', 'ORAL')),
    ai_confidence       DOUBLE PRECISION,
    ai_reason           TEXT,
    human_confirmation  TEXT CHECK (human_confirmation IS NULL OR human_confirmation IN ('KIDNEY', 'STOMACH', 'ORAL')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_screening_cases_status_id
    ON screening_cases (status, id DESC);

CREATE TABLE IF NOT EXISTS confirmed_cases (
    id            SERIAL PRIMARY KEY,
    reading_id    INTEGER NOT NULL UNIQUE REFERENCES screening_cases(id) ON DELETE CASCADE,
    organ         TEXT NOT NULL CHECK (organ IN ('KIDNEY', 'STOMACH', 'ORAL')),
    notes         TEXT,
    confirmed_by  TEXT,
    confirmed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_confirmed_cases_organ_id
    ON confirmed_cases (organ, id DESC);

CREATE TABLE IF NOT EXISTS decision_audit (
    id                        SERIAL PRIMARY KEY,
    reading_id                INTEGER NOT NULL REFERENCES screening_cases(id) ON DELETE CASCADE,
    selected_model            TEXT NOT NULL,
    llm_used                  SMALLINT NOT NULL CHECK (llm_used IN (0, 1)),
    specialist_results_json   JSONB NOT NULL,
    llm_result_json           JSONB,
    final_prediction          TEXT NOT NULL CHECK (final_prediction IN ('KIDNEY', 'STOMACH', 'ORAL')),
    final_confidence          DOUBLE PRECISION,
    final_reason              TEXT NOT NULL,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_decision_audit_reading_id
    ON decision_audit (reading_id, id DESC);

-- ---------------------------------------------------------------------------
-- Dashboard / product app
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS readings (
    id           SERIAL PRIMARY KEY,
    "timestamp"  TIMESTAMPTZ NOT NULL,
    ph           DOUBLE PRECISION NOT NULL,
    creatinine   DOUBLE PRECISION NOT NULL,
    urea         DOUBLE PRECISION NOT NULL,
    temperature  DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_readings_timestamp
    ON readings ("timestamp" DESC, id DESC);

CREATE TABLE IF NOT EXISTS patient_context (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    diagnosis    TEXT DEFAULT '',
    medications  TEXT DEFAULT '',
    notes        TEXT DEFAULT '',
    updated_at   TIMESTAMPTZ
);

INSERT INTO patient_context (id, diagnosis, medications, notes, updated_at)
VALUES (1, '', '', '', now())
ON CONFLICT (id) DO NOTHING;

-- Single-row table tracking the ESP32 sensor node's live WiFi status and
-- whether the dashboard has requested an on-demand sample.
CREATE TABLE IF NOT EXISTS device_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    ssid            TEXT,
    last_seen       TIMESTAMPTZ,
    pending_sample  BOOLEAN NOT NULL DEFAULT false
);

INSERT INTO device_state (id, ssid, last_seen, pending_sample)
VALUES (1, NULL, NULL, false)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS chat_messages (
    id          SERIAL PRIMARY KEY,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    lang        TEXT DEFAULT 'en',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Auth
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    name        TEXT DEFAULT '',
    phone       TEXT DEFAULT '',
    pass_salt   TEXT NOT NULL,
    pass_hash   TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Matches an inbound WhatsApp `from` number to a real patient (report/biomarkers/appointments Q&A).
CREATE INDEX IF NOT EXISTS idx_users_phone
    ON users (phone);

CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Appointments (WhatsApp booking) — replaces the old appointments.json file.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS appointments (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    phone        TEXT,
    slot_start   TIMESTAMPTZ NOT NULL,
    reason       TEXT NOT NULL,
    clinic       TEXT NOT NULL,
    branch       TEXT NOT NULL,
    channel      TEXT NOT NULL DEFAULT 'whatsapp',
    booked_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- One doctor / one slot at a time: this is what makes double-booking impossible.
    UNIQUE (slot_start)
);

CREATE INDEX IF NOT EXISTS idx_appointments_slot_start
    ON appointments (slot_start);

CREATE INDEX IF NOT EXISTS idx_appointments_user_id
    ON appointments (user_id, slot_start DESC);
