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

-- Persisted diet/self-care plan (single row) — regenerating from scratch and
-- "show me what I already have" are now different operations (see
-- routers/content_agents.py's `force` flag). NULL until generated once.
CREATE TABLE IF NOT EXISTS self_care_plan (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    plan_json    JSONB,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO self_care_plan (id, plan_json, updated_at)
VALUES (1, NULL, now())
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

-- Session expiry (security audit 2026-08-10 — tokens never expired before
-- this). Nullable add + backfill + NOT NULL keeps this idempotent and safe
-- to run against a table that already has rows.
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
UPDATE sessions SET expires_at = created_at + INTERVAL '30 days' WHERE expires_at IS NULL;
ALTER TABLE sessions ALTER COLUMN expires_at SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
    ON sessions (expires_at);

-- Deduplicates Meta WhatsApp webhook retries. Meta re-sends the exact same
-- inbound message if the server doesn't ack fast enough (the agent loop +
-- PDF generation can take well past that), and the webhook used to have no
-- way to tell a retry from a new message — replaying the whole agent loop
-- each time, which is why patients were getting the same report PDF sent to
-- them multiple times. See routers/whatsapp.py.
CREATE TABLE IF NOT EXISTS whatsapp_inbound_messages (
    message_id   TEXT PRIMARY KEY,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now()
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
    -- One doctor / one slot at a time among CONFIRMED bookings: see the partial
    -- unique index below, which replaced a plain table-wide UNIQUE(slot_start)
    -- so a cancelled slot can be rebooked while the cancelled row is kept for
    -- history (never delete a booking row).
    UNIQUE (slot_start)
);

CREATE INDEX IF NOT EXISTS idx_appointments_slot_start
    ON appointments (slot_start);

CREATE INDEX IF NOT EXISTS idx_appointments_user_id
    ON appointments (user_id, slot_start DESC);

-- Cancel/reschedule support (added 2026-08-14) — a cancelled appointment is
-- never deleted (full audit trail, same ethos as decision_audit elsewhere),
-- just marked cancelled so its slot frees up again. Nullable-free ADD COLUMN
-- with a default keeps this idempotent and safe against existing rows, same
-- pattern as the sessions.expires_at migration above.
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'confirmed';

-- Postgres has no "ADD CONSTRAINT IF NOT EXISTS" — guard via pg_constraint so
-- this stays safe to run repeatedly, like every other statement in this file.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'appointments_status_check'
    ) THEN
        ALTER TABLE appointments
            ADD CONSTRAINT appointments_status_check CHECK (status IN ('confirmed', 'cancelled'));
    END IF;
END $$;

-- Replace the table-wide UNIQUE(slot_start) above (Postgres auto-named it
-- appointments_slot_start_key, since it was declared as a table-level
-- UNIQUE(slot_start) constraint, not an inline column constraint) with a
-- partial unique index scoped to confirmed rows only, so a cancelled slot
-- becomes bookable again while the cancelled row itself is preserved.
ALTER TABLE appointments DROP CONSTRAINT IF EXISTS appointments_slot_start_key;
CREATE UNIQUE INDEX IF NOT EXISTS appointments_slot_start_confirmed_uidx
    ON appointments (slot_start) WHERE status = 'confirmed';

-- ---------------------------------------------------------------------------
-- Autonomous WhatsApp Agent (added 2026-08-19) — see
-- novera-whatsapp-autonomous-agent-spec.md. WhatsApp Agent gets its own
-- proactive triggers (screening completed, appointment completed, meal/
-- wellness check-ins) on top of replying to inbound messages.
-- ---------------------------------------------------------------------------

-- One post-visit follow-up per appointment, not per user — appointments
-- stays the single source of truth for booking state (per booking.py's own
-- docstring), so this is a column here rather than a duplicated status
-- field on whatsapp_patient_context below.
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS followup_sent BOOLEAN NOT NULL DEFAULT false;

-- Per-registered-user WhatsApp Agent memory: conversation state, the 24h
-- send-window gate, and check-in/self-care tracking. Deliberately NOT a
-- second copy of appointment status (see above) or the dashboard's
-- self_care_plan/patient_context tables (backed by a genuinely different
-- self-care plan than this one — this is what WhatsApp Agent generates
-- in-conversation, that's what the dashboard shows; both per-user as of
-- the multi-tenant migration below, added same day).
-- CORRECTION (2026-08-19, later same day): the note that used to be here
-- said screening data stays global/single-patient — that was reversed
-- within hours. See the multi-tenant isolation migration further down
-- this file; readings/screening_cases/patient_context/self_care_plan/
-- chat_messages are all per-user now.
CREATE TABLE IF NOT EXISTS whatsapp_patient_context (
    user_id                       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    conversation_summary          TEXT NOT NULL DEFAULT '',
    last_inbound_at               TIMESTAMPTZ,
    last_outbound_at              TIMESTAMPTZ,
    self_care_plan                TEXT,
    self_care_plan_issued_at      TIMESTAMPTZ,
    last_meal_checkin_at          TIMESTAMPTZ,
    last_meal_checkin_response    TEXT,
    last_wellness_checkin_at      TIMESTAMPTZ,
    -- Real cadence numbers are a product decision, not a technical one (see
    -- the spec's §8) — 3 is a placeholder default, configurable per row
    -- without a code change once a real number is decided.
    wellness_checkin_cadence_days INTEGER NOT NULL DEFAULT 3,
    reported_symptoms             JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Multi-tenant data isolation (added 2026-08-19, later same day as the
-- WhatsApp Agent work above). Every logged-in user used to see the exact
-- same readings/screening/self-care/doctor-notes data as every other user —
-- a real data-isolation bug for a health app, not cosmetic. Fixed here.
--
-- One physical shared ESP32 exists (not one-per-patient), so a reading has
-- no inherent owner — device_state.pending_sample_user_id (below) records
-- who armed the device for the next capture; POST /readings stamps that
-- onto the new row, then clears it. An unrequested/autonomous capture (the
-- firmware's periodic 5-minute auto-send) lands with user_id = NULL —
-- orphaned, invisible on every dashboard. Accepted, intentional consequence
-- of the shared-device model, not a bug.
-- ---------------------------------------------------------------------------

ALTER TABLE readings ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_readings_user_id ON readings (user_id, "timestamp" DESC, id DESC);

ALTER TABLE screening_cases ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_screening_cases_user_id ON screening_cases (user_id, id DESC);

ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages (user_id, id ASC);

ALTER TABLE device_state ADD COLUMN IF NOT EXISTS pending_sample_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

-- patient_context / self_care_plan: were singletons (id INTEGER PRIMARY KEY
-- CHECK (id = 1)) — that PRIMARY KEY must actually be dropped, not just
-- left alone, or it's physically impossible to ever insert a second
-- per-user row regardless of what user_id says. Dropped by catalog lookup
-- (not a guessed constraint name) so this can't silently no-op. The
-- existing single id=1 row in each table becomes permanently orphaned
-- (user_id IS NULL) — same accepted consequence as readings above, not
-- backfilled to a guessed owner.
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN SELECT conname FROM pg_constraint WHERE conrelid = 'patient_context'::regclass AND contype IN ('p', 'c')
    LOOP
        EXECUTE 'ALTER TABLE patient_context DROP CONSTRAINT ' || quote_ident(r.conname);
    END LOOP;
END $$;
ALTER TABLE patient_context ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'patient_context_user_id_key') THEN
        ALTER TABLE patient_context ADD CONSTRAINT patient_context_user_id_key UNIQUE (user_id);
    END IF;
END $$;

DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN SELECT conname FROM pg_constraint WHERE conrelid = 'self_care_plan'::regclass AND contype IN ('p', 'c')
    LOOP
        EXECUTE 'ALTER TABLE self_care_plan DROP CONSTRAINT ' || quote_ident(r.conname);
    END LOOP;
END $$;
ALTER TABLE self_care_plan ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'self_care_plan_user_id_key') THEN
        ALTER TABLE self_care_plan ADD CONSTRAINT self_care_plan_user_id_key UNIQUE (user_id);
    END IF;
END $$;
