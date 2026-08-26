-- NOVERA — PostgreSQL schema.
-- Idempotent: safe to run repeatedly (CREATE TABLE/INDEX IF NOT EXISTS).

-- ---------------------------------------------------------------------------
-- Screening pipeline (novera.py's deterministic organ-screening core)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS reference_ranges (
    id          SERIAL PRIMARY KEY,
    organ       TEXT NOT NULL CHECK (organ IN ('KIDNEY', 'LIVER', 'ORAL')),
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
    ai_prediction       TEXT CHECK (ai_prediction IS NULL OR ai_prediction IN ('KIDNEY', 'LIVER', 'ORAL')),
    ai_confidence       DOUBLE PRECISION,
    ai_reason           TEXT,
    human_confirmation  TEXT CHECK (human_confirmation IS NULL OR human_confirmation IN ('KIDNEY', 'LIVER', 'ORAL')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_screening_cases_status_id
    ON screening_cases (status, id DESC);

CREATE TABLE IF NOT EXISTS confirmed_cases (
    id            SERIAL PRIMARY KEY,
    reading_id    INTEGER NOT NULL UNIQUE REFERENCES screening_cases(id) ON DELETE CASCADE,
    organ         TEXT NOT NULL CHECK (organ IN ('KIDNEY', 'LIVER', 'ORAL')),
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
    final_prediction          TEXT NOT NULL CHECK (final_prediction IN ('KIDNEY', 'LIVER', 'ORAL')),
    final_confidence          DOUBLE PRECISION,
    final_reason              TEXT NOT NULL,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_decision_audit_reading_id
    ON decision_audit (reading_id, id DESC);

-- Tamper-evidence (2026-08-26): decision_audit is the AI Safety/auditability
-- record of every screening decision ever made — application code already
-- never UPDATEs or DELETEs a row after insert (verified by reading every
-- call site), but until now that was only a code convention, not a
-- DB-enforced guarantee — a future code change, or anyone with direct DB
-- access, could silently alter or erase a row with no trace. This trigger
-- makes append-only a real, testable database property instead.
CREATE OR REPLACE FUNCTION decision_audit_block_mutation() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'decision_audit is append-only: % is not permitted (id=%)', TG_OP, OLD.id;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS decision_audit_no_mutation ON decision_audit;
CREATE TRIGGER decision_audit_no_mutation
    BEFORE UPDATE OR DELETE ON decision_audit
    FOR EACH ROW EXECUTE FUNCTION decision_audit_block_mutation();

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

-- Multi-tenant since 2026-08-19 (see the migration further down this file,
-- which drops the id=1 singleton constraint and promotes user_id to the
-- real key) — no more global seed row here. reference_data.get_context()
-- creates a row per-user on first access instead.
CREATE TABLE IF NOT EXISTS patient_context (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    diagnosis    TEXT DEFAULT '',
    medications  TEXT DEFAULT '',
    notes        TEXT DEFAULT '',
    updated_at   TIMESTAMPTZ
);

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

-- Persisted diet/self-care plan — regenerating from scratch and "show me
-- what I already have" are now different operations (see
-- routers/content_agents.py's `force` flag). NULL until generated once.
-- Multi-tenant since 2026-08-19 (see the migration further down this file)
-- — no more global seed row here, one row is upserted per-user on demand.
CREATE TABLE IF NOT EXISTS self_care_plan (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    plan_json    JSONB,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

-- A duplicate phone across two accounts makes _find_user_by_phone's lookup
-- ambiguous (whichever row Postgres happens to return "wins" the WhatsApp
-- thread) — app/security.py now rejects new signups that would collide, and
-- this is the DB-level backstop. Guarded: only add the constraint if no
-- collision already exists, so this migration can never fail/break a
-- deploy the way an unconditional CREATE UNIQUE INDEX could on data that
-- predates the app-level check.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM users WHERE phone <> '' GROUP BY phone HAVING COUNT(*) > 1
    ) THEN
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_unique ON users (phone) WHERE phone <> '';
    ELSE
        RAISE NOTICE 'idx_users_phone_unique skipped: duplicate phone(s) already exist on users';
    END IF;
END $$;

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
-- BUG FIX (found live in production, 2026-08-19): dropping a PRIMARY KEY
-- does NOT drop the underlying NOT NULL on that column — that's a separate
-- attnotnull flag, not a pg_constraint row, so the loop above never touched
-- it. Every upsert that omits `id` (all of them now — nothing generates it
-- anymore, no sequence was ever attached, this was a plain INTEGER PK, not
-- SERIAL) was failing with "null value in column id violates not-null
-- constraint" until this line was added.
ALTER TABLE patient_context ALTER COLUMN id DROP NOT NULL;
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
ALTER TABLE self_care_plan ALTER COLUMN id DROP NOT NULL;
ALTER TABLE self_care_plan ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'self_care_plan_user_id_key') THEN
        ALTER TABLE self_care_plan ADD CONSTRAINT self_care_plan_user_id_key UNIQUE (user_id);
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Store: device + strip-bundle purchases (added 2026-08-20). No subscription
-- of any kind — every order is one-time. Pricing is never trusted from the
-- client: routers/orders.py always re-prices from app/core/catalog.py
-- server-side. Guest checkout is allowed (see spec) so user_id is nullable.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS orders (
    id                  SERIAL PRIMARY KEY,
    -- Opaque, unguessable public identifier for GET /api/orders/{token} and
    -- the post-payment confirmation page — never the sequential id, so an
    -- order can't be enumerated/guessed by walking integers (IDOR).
    order_token         TEXT NOT NULL UNIQUE,
    user_id             INTEGER REFERENCES users(id) ON DELETE SET NULL,
    email               TEXT NOT NULL,
    phone               TEXT NOT NULL,
    shipping_address    JSONB NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'paid', 'cancelled', 'failed')),
    currency            TEXT NOT NULL DEFAULT 'OMR',
    total_baisa         INTEGER NOT NULL CHECK (total_baisa >= 0),
    thawani_session_id  TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders (user_id, created_at DESC);

-- Device and bundle stay separate line items even in the same order — never
-- collapsed into one SKU — so device revenue and bundle revenue are two
-- separate, queryable lines for the financial model (item_type), per spec.
CREATE TABLE IF NOT EXISTS order_items (
    id                  SERIAL PRIMARY KEY,
    order_id            INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    sku                 TEXT NOT NULL CHECK (sku IN ('DEVICE', 'STARTER', 'VALUE', 'PRO')),
    item_type           TEXT NOT NULL CHECK (item_type IN ('device', 'bundle')),
    name                TEXT NOT NULL,
    unit_price_baisa    INTEGER NOT NULL CHECK (unit_price_baisa >= 0),
    quantity            INTEGER NOT NULL CHECK (quantity > 0),
    line_total_baisa    INTEGER NOT NULL CHECK (line_total_baisa >= 0)
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items (order_id);

-- ---------------------------------------------------------------------------
-- Organ rename: STOMACH -> LIVER (2026-08-20). The screening panel's third
-- organ was always meant to read "Liver" in the workflow, not "Stomach" —
-- same 4 biomarkers/reference ranges, just the wrong label. The CREATE TABLE
-- statements above already say LIVER for fresh installs; on a database that
-- already has these tables (CREATE TABLE IF NOT EXISTS no-ops on those), the
-- CHECK constraints and any already-stored 'STOMACH' values need moving by
-- hand — same guarded, idempotent style as appointments_status_check above.
-- Relabels history rather than leaving 'STOMACH' as an orphaned legacy value
-- forever: a past screening that predicted the old "stomach" organ is the
-- exact same liver-panel result under its correct name now, not a different
-- fact.
-- ---------------------------------------------------------------------------
-- Bug fix (2026-08-22): these DROP CONSTRAINTs used to run AFTER the UPDATEs
-- below, so on any database still holding the pre-rename constraints (every
-- deploy since this migration was written), the very first UPDATE — setting
-- organ = 'LIVER' on a still-'STOMACH'-only CHECK constraint — threw an
-- uncaught CheckViolation. init_db.py's pre-deploy step has been crashing on
-- this exact statement ever since, so Railway never promoted a single deploy
-- past this migration; the old pre-rename container just kept serving
-- traffic indefinitely. Constraints must come off before the data that
-- violates them gets written, not after.
ALTER TABLE reference_ranges DROP CONSTRAINT IF EXISTS reference_ranges_organ_check;
ALTER TABLE screening_cases DROP CONSTRAINT IF EXISTS screening_cases_ai_prediction_check;
ALTER TABLE screening_cases DROP CONSTRAINT IF EXISTS screening_cases_human_confirmation_check;
ALTER TABLE confirmed_cases DROP CONSTRAINT IF EXISTS confirmed_cases_organ_check;
ALTER TABLE decision_audit DROP CONSTRAINT IF EXISTS decision_audit_final_prediction_check;

UPDATE reference_ranges SET organ = 'LIVER' WHERE organ = 'STOMACH';
UPDATE screening_cases SET ai_prediction = 'LIVER' WHERE ai_prediction = 'STOMACH';
UPDATE screening_cases SET human_confirmation = 'LIVER' WHERE human_confirmation = 'STOMACH';
UPDATE confirmed_cases SET organ = 'LIVER' WHERE organ = 'STOMACH';
UPDATE decision_audit SET final_prediction = 'LIVER' WHERE final_prediction = 'STOMACH';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'reference_ranges_organ_check') THEN
        ALTER TABLE reference_ranges ADD CONSTRAINT reference_ranges_organ_check CHECK (organ IN ('KIDNEY', 'LIVER', 'ORAL'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'screening_cases_ai_prediction_check') THEN
        ALTER TABLE screening_cases ADD CONSTRAINT screening_cases_ai_prediction_check CHECK (ai_prediction IS NULL OR ai_prediction IN ('KIDNEY', 'LIVER', 'ORAL'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'screening_cases_human_confirmation_check') THEN
        ALTER TABLE screening_cases ADD CONSTRAINT screening_cases_human_confirmation_check CHECK (human_confirmation IS NULL OR human_confirmation IN ('KIDNEY', 'LIVER', 'ORAL'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'confirmed_cases_organ_check') THEN
        ALTER TABLE confirmed_cases ADD CONSTRAINT confirmed_cases_organ_check CHECK (organ IN ('KIDNEY', 'LIVER', 'ORAL'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'decision_audit_final_prediction_check') THEN
        ALTER TABLE decision_audit ADD CONSTRAINT decision_audit_final_prediction_check CHECK (final_prediction IN ('KIDNEY', 'LIVER', 'ORAL'));
    END IF;
END $$;
