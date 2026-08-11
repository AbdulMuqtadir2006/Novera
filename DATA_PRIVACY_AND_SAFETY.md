# Novera — Data Privacy & AI Safety

**Status:** Living document, current as of the codebase in this repository.
**Audience:** Technical evaluators, judging panels, and internal engineering reference.

This document has two purposes. First, to make visible a set of safety mechanisms that already exist in the Novera backend but are invisible from the outside because they live in server-side code a demo or pitch deck never shows. Second, to state plainly where the system currently falls short of production-grade data-privacy and safety practice, and what it would take to close each gap.

Every claim below is grounded in a specific file and function in this repository, not in aspirational description. File paths are relative to `backend/`.

---

## Part 1 — What already exists

### 1.1 No-fabrication guarantee on the screening decision

The organ-screening pipeline (`app/core/screening_llm.py`, `app/core/scoring.py`) is built around one hard rule: **if the AI call fails or returns something invalid, no result is saved — ever.**

The deterministic part of the pipeline (`scoring.ScoringEngine.evaluate` in `app/core/scoring.py`) computes a range-fit score and a similarity score against a bounded set of prior confirmed cases for each of the three candidate organs (KIDNEY, STOMACH, ORAL) using fixed reference ranges. Only after that math is done does the pipeline make **exactly one** OpenRouter call (`screening_llm.decide`) to pick a single final organ from those pre-computed numbers. The system prompt explicitly forbids inventing thresholds or historical cases: *"Use only the supplied evidence... Do not invent medical thresholds, diagnoses, or historical cases."*

The failure path is what matters most for safety. In `process_case_stream` (`app/core/screening_llm.py`, lines ~163–177):

```python
try:
    decision, model, raw_result = decide(reading, specialist_results)
except OpenRouterDecisionError:
    scoring.release_reading(reading["id"])
    ...
```

`scoring.release_reading()` (`app/core/scoring.py`, lines 227–236) does this:

```python
def release_reading(reading_id: int) -> None:
    """Return a failed OpenRouter case to NEW without saving a fake prediction (req 8)."""
    db.execute(
        """
        UPDATE screening_cases
        SET status = 'NEW', ai_prediction = NULL, ai_confidence = NULL, ai_reason = NULL
        WHERE id = %s
        """,
        (reading_id,),
    )
```

The case is reverted to `NEW` and every AI-derived field (`ai_prediction`, `ai_confidence`, `ai_reason`) is explicitly nulled. The caller receives a `RETRY_REQUIRED` status with an honest message, not a plausible-looking guess.

**Contrast with a naive implementation:** a common shortcut is to catch the exception and fall back to "pick the highest-scoring organ from the deterministic pass," or retry silently until *something* comes back and present it identically to a real AI decision. Novera does neither. A malformed response, a timeout, an out-of-vocabulary prediction, or an empty reason string all route through the same `OpenRouterDecisionError` path and produce zero persisted prediction. No code path in this pipeline writes an `ai_prediction` value that didn't come from a validated, schema-checked model response.

### 1.2 Full decision audit trail

Every successful screening decision writes a row to `decision_audit` (`db/schema.sql`, lines 50–64), not just the final answer:

```sql
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
```

`scoring.persist_decision()` (`app/core/scoring.py`, lines 239–276) writes this row in the same database transaction as the `screening_cases` update, so the audit trail and the outcome can never diverge. It captures the **actual model string** returned by OpenRouter's response metadata (`app/core/screening_llm.py` line 121, not just the model requested — so a silent OpenRouter reroute is recorded, not hidden), **every organ's** range score, similarity score, combined score, and matched-case count (not just the winner), and the **raw prediction/confidence/reason** the LLM returned before any further processing.

This means any flagged screening decision can be reconstructed after the fact: which model ran, what every specialist score was, and exactly what the model said and why. This is the technical basis for "traceability" as a queryable property of the system, not a claim.

### 1.3 Source tagging on all generated content

The four content agents — voice narration, patient report, self-care plan, and chat (`app/core/content_llm.py`) — each attempt one OpenRouter call and, on any failure (LLM unreachable, invalid JSON, schema validation failure), fall back to a deterministic bilingual template (`app/core/fallbacks.py`). Critically, **every response from either path is tagged with its origin**:

```python
return {"script": out.script, "source": "ai"}
...
return fallbacks.voice(reading, lang)   # returns {"script": ..., "source": "fallback"}
```

This pattern repeats identically across `voice_agent`, `report_agent`, `self_care_agent`, and `chat_agent` in `app/core/content_llm.py`, and each corresponding function in `app/core/fallbacks.py` independently sets `"source": "fallback"`. The two code paths cannot accidentally converge on the same tag — they are written and set separately, in different files, by design.

The practical effect: the frontend, or any downstream consumer of the API, can always distinguish "generated by the model right now" from "a fixed, pre-written safety-net response because the model was unavailable." Nothing generated deterministically is ever silently presented as an AI judgment, and vice versa — an auditor of patient-facing output has a machine-readable way to know which is which.

### 1.4 WhatsApp Q&A grounding constraint

The WhatsApp assistant (`app/core/whatsapp_agent.py`) answers patient questions about their own report, biomarkers, doctor notes, and appointments. Before any LLM call happens, `_gather_patient_facts()` (lines 57–77) pulls only real rows from Postgres — the latest reading, doctor context, upcoming appointments, and the most recent completed screening case — and `_facts_to_text()` (lines 80–118) renders them into a plain-text fact sheet.

The system prompt in `_answer_question()` (`app/core/whatsapp_agent.py`, lines 130–148) is explicit and quoted here verbatim:

> *"You are NOVERA's WhatsApp assistant. Answer the patient's question using ONLY the facts supplied below — never invent a biomarker value, diagnosis, prediction, or appointment time that isn't in the facts. If the facts don't contain the answer, say so plainly and suggest checking the app... This is screening support, not medical advice."*

If the OpenRouter call itself fails (`LLMError`), the code does not retry into a hallucination risk or return an error to the patient. It falls back to `_fallback_answer()` (lines 121–127), which returns the **same fact sheet as raw structured text**, not a model-generated approximation of it:

```python
def _fallback_answer(facts: dict[str, Any], lang: str) -> str:
    """Deterministic answer built directly from the same facts — used only if
    the OpenRouter phrasing call fails. Never invents a value..."""
    return _facts_to_text(facts) if lang != "ar" else (
        "إليك آخر ما لدينا من بيانات:\n" + _facts_to_text(facts)
    )
```

The worst case when the LLM is unavailable is a slightly less conversational message — never a fabricated fact. Same no-fabrication principle as §1.1, applied to the conversational surface.

### 1.5 Deterministic booking, race-safe by database constraint

Appointment booking (`app/core/booking.py`) never calls an LLM. `find_and_book_slot()` computes the next candidate slot from clinic hours (`app/core/clinic.py`) and writes it with:

```sql
INSERT INTO appointments (...) VALUES (...)
ON CONFLICT (slot_start) DO NOTHING
RETURNING id, slot_start, ...
```

against the schema constraint (`db/schema.sql`, lines 153–165):

```sql
CREATE TABLE IF NOT EXISTS appointments (
    ...
    slot_start   TIMESTAMPTZ NOT NULL,
    ...
    UNIQUE (slot_start)
);
```

Double-booking is prevented at the database layer, not by application-level checking, which is inherently racy under concurrent requests (two patients confirming a slot at the same moment) and easy to get wrong. Here, even a broken or compromised calling path cannot produce two appointments in the same slot — Postgres rejects the second insert outright, and `find_and_book_slot` simply advances to the next slot and retries (bounded to `MAX_SLOT_ATTEMPTS = 96`, roughly two days of 30-minute slots). The LangGraph/LLM layer that decides *when* to call this function never invents a specific appointment time itself — it only ever asks `booking.py` for "the next available slot," per the module's own docstring.

### 1.6 Human-in-the-loop by design — this *is* the oversight mechanism

This is the point most relevant to "AI Safety, Ethics & Oversight" as a judging criterion, and it should be named explicitly: **Novera's AI never outputs a standalone diagnosis that terminates the patient's journey.** Every flagged case's resolution path is the same — book a real appointment at a real, named clinic (Badr Al Samaa, Al Khuwair branch — `app/config.py` lines 40–44) for a human clinician to examine the patient and make the actual clinical call.

The system prompt for the screening decision itself states this constraint on the model: *"This is experimental screening support, not a confirmed diagnosis"* (`app/core/screening_llm.py`, line 82). The content agents repeat it: the voice agent is told to *"always note it is research-stage, not medical advice"*; the report and self-care agents both work under the same framing, and every fallback response carries a bilingual disclaimer (`fallbacks.RESEARCH_LINE`) stating Novera is *"a research-stage screening platform — not a diagnostic device."*

In other words, the AI's job is bounded to triage and pattern-flagging; the clinical decision is always deferred to a human. This is a structural property of the system — the code path from "flagged" to "resolved" always passes through `booking.py` and a real clinic — not a disclaimer bolted on after the fact.

---

## Part 2 — Real current gaps and remediation plan

This section is intentionally unflattering. An evaluator will find these issues by reading the code; better that they read Novera's own honest account of them first.

### 2.1 Auth is demo-grade, by the code's own admission

`app/security.py` opens with this docstring: *"Demo-grade: sufficient for a research/demo app, not a hardened production auth system."* This is accurate. Password hashing uses `scrypt` with a random 16-byte salt and constant-time comparison (`hmac.compare_digest`) — a reasonable choice, not a weak one. But:

- No multi-factor authentication.
- No password complexity requirement beyond a 6-character minimum (`app/security.py` line 68: `if not password or len(password) < 6`).
- Session tokens are 32-byte random hex (`secrets.token_hex(32)`), which is cryptographically fine, but there is no session revocation UI, no per-device session listing, and no anomaly detection (e.g., login from a new location).

**Remediation:** raise minimum password length to 10–12 characters with a basic common-password check (**~1–2 hours**); add a "log out of all sessions" endpoint deleting all `sessions` rows for a user, trivial given the existing schema (**~1 hour**); add MFA (TOTP) before handling real patient data — needs a new `mfa_secrets` table, enrollment flow, and frontend UI (**~1–2 days**, pre-production requirement, not urgent for a prototype).

### 2.2 `POST /api/readings` has no authentication

This is the most concrete gap in the system. `app/routers/readings.py`, line 43:

```python
@router.post("/readings", status_code=201)
def add_reading(body: ReadingIn):
```

Unlike every other endpoint in this router (`GET /readings/latest`, `GET /readings`), which require `Depends(require_user)`, the POST endpoint has **no auth dependency at all**. Anyone who knows or guesses the URL can POST a fabricated biomarker reading, and it will be inserted into `readings` and immediately treated as the patient's latest live sample.

**Why this exists:** this endpoint is the ESP32 biosensor device's ingestion path. The physical device currently has no credential of its own — it's a microcontroller pushing HTTP requests over WiFi, and no device-identity mechanism was built for it yet. This is a real, current gap, not a hypothetical one: as written, the endpoint trusts any caller.

**Remediation:** add a static shared-secret header (e.g., `X-Device-Key`) checked against an environment variable (`DEVICE_API_KEY`) before accepting the POST, rejecting with 401 if absent or mismatched — no change to the ESP32's HTTP capability required, just one extra header and one server-side `if` check (**~1 hour**, plus flashing the key onto device firmware). Longer-term, move to per-device API keys (a `devices` table with a hashed key per unit) so a lost or compromised device can be revoked individually rather than rotating one shared secret fleet-wide (**~1 day**, worth doing once more than one device is in the field). This should be treated as the top-priority fix in this document — it's the one gap that's both trivial to exploit and non-trivial in consequence, since fake readings feed directly into the screening pipeline in §1.1.

### 2.3 Encryption at rest — unconfirmed, needs verification

The Postgres database is Railway-managed (`DATABASE_URL` is read from environment in `app/config.py`, no self-hosted database config present in this repo). Nothing in this codebase configures, disables, or documents encryption-at-rest for the underlying storage. That means this document cannot honestly claim either "data is encrypted at rest" or "data is not encrypted at rest" — it is **unverified from code alone**, and it would be dishonest to guess.

**Remediation:** confirm Railway's current at-rest encryption posture for managed Postgres directly with Railway (docs/support) and record the answer here (**~30 minutes**, blocked only on getting a straight answer from the platform). If that's unsatisfactory or unavailable, consider column-level encryption (e.g., `pgcrypto`) for the most sensitive free-text fields — `patient_context.diagnosis`, `patient_context.medications`, `patient_context.notes`, `confirmed_cases.notes` — so a raw database dump doesn't expose readable clinical text (**~1 day**, including a real key-management decision and updating read/write paths in `app/core/reference_data.py`). This is the kind of item that genuinely needs a data-protection-officer-level review before Novera handles real patient data at scale, not something to resolve unilaterally in code.

### 2.4 No data retention or deletion policy

Nothing in `db/schema.sql` enforces a TTL on any table. `readings`, `chat_messages`, `screening_cases`, and `decision_audit` all accumulate indefinitely. The only deletion path in the entire system is `DELETE /api/chat` (`app/routers/content_agents.py`, line 89), which wipes the whole `chat_messages` table — not a per-user, "delete my data" flow, and it doesn't touch readings, screening history, or appointments at all.

**Remediation:** define an explicit retention policy (e.g., raw `readings` older than N months archived, `chat_messages` older than N months purged) — this is a **product/legal decision first**, engineering second (~1 day for a scheduled cleanup job once decided). Build a real "delete my account and data" endpoint cascading across `users`, `sessions`, `appointments` (already `ON DELETE SET NULL` via FK), and `chat_messages` — **~1 day**, complicated by the fact that `chat_messages` and `readings` currently have no `user_id` column at all (single-tenant tables in the current schema), so this is a schema question as much as a query.

### 2.5 No consent flow at signup

`security.create_user()` (`app/security.py`, lines 64–87) validates email format, password length, and phone format, and inserts the user. There is no step — in this function or anywhere in the signup router — that shows a data-handling/privacy notice or records that the user agreed to one before their health data starts being collected.

**Remediation:** add a required checkbox/screen in the signup flow ("I agree to how Novera collects and uses my saliva-screening data") and a `consent_accepted_at TIMESTAMPTZ` column on `users`, set at signup — **~2–4 hours** for the backend column and check; the larger cost is writing the actual privacy-notice text, a content/legal task, not a coding one.

### 2.6 What's already fine — stated plainly, not just implied

Two things worth stating as genuine positives rather than leaving unmentioned, since a fair account of gaps should also credit what's already correct:

- **CORS is properly restricted.** `app/config.py` (lines 55–66) sets `CORS_ORIGINS` to an explicit allow-list (the production domains, local dev ports, and the Capacitor Android WebView origin), not a wildcard. This is standard practice, done correctly.
- **The WhatsApp webhook verifies its signature and fails closed.** `app/routers/whatsapp.py`, `_valid_signature()` (lines 28–34) computes an HMAC-SHA256 over the raw request body using `META_APP_SECRET` and compares it to Meta's `X-Hub-Signature-256` header with `hmac.compare_digest`. If `META_APP_SECRET` isn't configured, the function returns `False` unconditionally — the code comment states the reasoning directly: *"Fail closed: with no app secret configured, authenticity can't be verified at all, so reject rather than silently trust everything."* This is the correct failure mode and it's easy to get backwards (many implementations default to trusting the request when the secret is merely misconfigured); Novera doesn't.

---

## AI Ethics Statement

Novera is a research-stage saliva-biosensor screening platform, not a diagnostic device. Every AI component in the system — the organ-screening decision, the patient-facing report and self-care content, and the WhatsApp assistant — is explicitly instructed, in its own system prompt, that it is producing screening support, not a medical diagnosis, and every one of those prompts says so in plain language to the model itself, not just in marketing copy.

The system is built so that an AI failure never becomes a fabricated result. If the screening model's call fails or returns something invalid, the case is reverted to unprocessed and no prediction is saved — there is no code path that lets a broken AI call quietly produce a plausible-looking answer. Every content response, whether AI-generated or produced by a deterministic fallback, is tagged with its true origin, so nothing generated by a safety-net template is ever presented as an AI judgment. Every screening decision that does complete writes a full audit record — the model used, every candidate organ's score, and the model's raw output — so any flagged case can be reconstructed and reviewed after the fact.

Most importantly, Novera's AI does not close the loop on its own. Every flagged case routes to booking a real appointment with a named clinic for a human clinician to examine the patient and make the actual medical determination. The AI's role is triage and pattern-flagging under a hard non-fabrication guarantee; the clinical decision — the part that actually matters to a patient's health — is always made by a person. That handoff, enforced structurally in the code rather than asserted as a policy, is Novera's answer to what human oversight of an agentic health-AI system should look like.
