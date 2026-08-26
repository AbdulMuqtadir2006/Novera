# NOVERA — AI Safety, Security & Reliability Validation Report

**Prepared:** 2026-08-26, ahead of the 2026-08-30/31 Final Evaluation
**Scope:** A two-round, code-level audit and hardening pass across the live NOVERA backend
(`api.novera.fun`) and frontend (`novera.fun`), explicitly targeting the evaluation categories
below. This is a factual record of what was checked, what was found, what was changed, and how
each change was verified — written so it can be turned into a competition report without
overstating what was actually done.

**Methodology note:** every finding came from reading the actual, deployed source code — not from
documentation, not from assumptions. Every fix was verified by an automated check (syntax
compilation, a full application import, or a targeted logic test with real assertions) before being
committed. Section 6 lists the small number of things that could **not** be verified in this
environment, stated plainly rather than glossed over.

---

## 1. Evaluation categories covered

This work was scoped against the categories used by AI Verify, Project Moonshot, NIST AI RMF/TEVV,
and standard LLM red-team methodology:

| Category | Result |
|---|---|
| Prompt injection resistance | Reviewed — already solid, no changes needed |
| Tool-calling safety / authorization | **1 finding, fixed** |
| Privacy / data-leakage | **1 finding, fixed** (+ 1 disclosure gap, fixed) |
| Hallucination | Reviewed — already solid, no changes needed |
| Medical-response safety | **2 findings, fixed** |
| Agentic autonomy | **1 finding, fixed** |
| Reliability / failure handling | Reviewed — already solid, no changes needed |
| Human oversight | **1 finding, fixed** |
| Auditability | **1 finding, fixed** |
| Supply chain / dependency hygiene | Reviewed — known, low-value-to-fix-this-week gaps noted |
| Web authentication & session security | Reviewed — already solid, no changes needed |
| Payment/checkout security | Reviewed — already solid, no changes needed |
| SQL injection | Swept — zero instances found |
| Frontend XSS | Swept — zero instances found |
| CI/CD workflow security | Reviewed — already solid, no changes needed |

---

## 2. Findings and fixes, in detail

### 2.1 Tool-calling safety — autonomous agents could commit real bookings

**Finding:** The WhatsApp agent's real-world write tools (`book_appointment`, `cancel_appointment`,
`reschedule_appointment`) were available to every trigger, including fully autonomous ones
(`wellness.checkin`, `mealtime.checkin`, `sensor.reading_received`) — restrained only by a sentence
in the AI's instructions ("only call this once the patient has agreed"), not by anything in the code.

**Fix:** Added an `allow_booking` parameter to the tool-builder function. The exclusively-autonomous
entry point now hardcodes `allow_booking=False` — the booking tools are structurally absent from the
model's toolset on that path, not just discouraged. An autonomous run can still *offer* an
appointment; only a patient's own reply can *commit* one.

**Verification:** Called the tool-builder function directly with both settings and inspected the
actual list of tool names returned, confirming `book_appointment`/`cancel_appointment`/
`reschedule_appointment` are present on the reactive path and genuinely absent on the proactive path,
while the read-only slot-preview tool remains available on both.

### 2.2 Privacy / data-leakage — two device endpoints had zero authentication

**Finding:** `POST /api/readings` (the endpoint the physical sensor posts biomarker data to) and
`POST /device/ping` (which can return a patient's first name) had no authentication of any kind —
anyone on the internet could call either directly.

**Fix:** Added a device-key check (`X-Device-Key` header, checked against a new `DEVICE_API_KEY`
environment variable) to both endpoints. Deliberately a no-op until the key is actually configured,
so the real physical device isn't locked out before it's reflashed with the matching key.

**Verification:** Confirmed programmatically that with the key unset, both endpoints behave exactly
as before (no regression); with the key set, a request without the correct header is rejected and a
request with it is accepted.

**Status:** Code is deployed. **Not yet enforced in production** — requires setting the environment
variable on the hosting platform and reflashing the physical device with the matching key. This is
the one outstanding manual step from this entire pass.

### 2.3 Privacy — third-party AI data processors were undisclosed

**Finding:** Patient health data (biomarker readings, doctor context, symptoms) is sent to
OpenRouter (which routes to DeepSeek and Anthropic) for every screening decision, report, and chat
interaction. Nothing on the public-facing safety page disclosed this.

**Fix:** Added a disclosure sentence to the safety page's encryption/data-security section naming the
providers and clarifying that only the minimum data needed per request is sent, and it is never sold
or shared beyond that.

### 2.4 Medical-response safety — no emergency-message handling on either chat surface

**Finding:** Neither the WhatsApp agent nor the website's self-care chat had any deterministic
handling for a message describing a real medical emergency (e.g. "I can't breathe," "I want to hurt
myself"). Both relied entirely on the underlying AI model's judgment in the moment, with no
code-level backstop.

**Fix:** Built a shared, deterministic (non-AI) keyword-matching module used by both surfaces. A
message matching a fixed list of high-specificity emergency phrases (English and Arabic — chest
pain, can't breathe, suicidal ideation, self-harm language, and similar) skips the AI model entirely
and receives an instant, hardcoded reply directing the person to call Oman's emergency number or go
to the nearest emergency room.

**Verification:** Tested the matcher directly against known emergency phrasings (including the
specific "I want to hurt myself" case, in both English and Arabic) and against ordinary
symptom-related questions (e.g. "is mild stomach pain normal after eating?") to confirm no false
positives. Confirmed both the WhatsApp and website chat code paths call the same shared function.

### 2.5 Medical-response safety — safety-page claim didn't match the deployed system

**Finding:** The public AI-safety page stated the AI "books an appointment" as one of its autonomous
actions — which was accurate when written, but became false the moment the fix in §2.1 shipped.

**Fix:** Corrected the wording to state that the AI can offer an appointment autonomously, but
committing a real booking always requires the patient's own reply.

### 2.6 Agentic autonomy & human oversight — the forced human-review mechanism was silently inert

**Finding:** The system has a "safety floor" meant to guarantee that any patient with a concerning
screening result gets proactively contacted, no exceptions. In the current production configuration,
patient-facing risk flags are temporarily suppressed to "low" for every case (a deliberate, separate
decision while sensor calibration is being finalized) — but the safety-floor mechanism was reading
that same suppressed flag, meaning it could never actually trigger in the current configuration. The
underlying numerical concern score was still being computed and stored correctly the entire time;
only the escalation mechanism was blind to it.

**Fix:** The safety-floor check now also evaluates the real, never-suppressed underlying score
directly, independent of whether the patient-facing flag has been suppressed for calibration reasons.
A genuinely concerning result now reaches the escalation mechanism regardless of that separate,
unrelated suppression setting.

**Verification:** Constructed both scenarios directly (a suppressed-flag-but-concerning-score case,
and a genuinely-low-score case) against the actual decision function and confirmed the escalation
fires only in the first case.

### 2.7 Auditability — the decision audit trail wasn't tamper-evident

**Finding:** Every screening decision is logged to a permanent audit record. Application code never
modifies or deletes these records after creation — but nothing in the database enforced that; it was
a coding convention, not a guarantee.

**Fix:** Added a database-level trigger that rejects any attempt to update or delete an audit record,
turning "append-only" into an enforced property of the database itself rather than an assumption
about how the code happens to behave today or in the future.

**Verification:** Reviewed for syntax correctness against an established, already-working pattern
elsewhere in the same database schema file. **Not executed against a live database in this
environment** — see §6.

### 2.8 Reviewed and confirmed solid — no changes required

The following were specifically checked and found to already meet a high bar, so no changes were
made:

- **Prompt injection:** Tool authorization is bound to server-verified identity (the sender's phone
  number from a cryptographically verified webhook), not derived from message text. Nearly all
  real-world-effect tools take no arguments at all, leaving no field for injected text to manipulate.
- **Hallucination:** The screening-decision AI is contractually bound by its instructions to use only
  the evidence it's given; a failed, invalid, or malformed response causes the case to revert to
  "needs retest" rather than saving any invented result. Verified this holds in both the direct
  failure path and the fallback path.
- **Web authentication:** Passwords are hashed with a modern, deliberately slow algorithm (scrypt)
  with per-user random salting and constant-time comparison (resistant to timing attacks). Sessions
  are server-side, opaque, and immediately revocable on logout — not a long-lived unrevocable token.
  Login and signup are both rate-limited against brute-force/credential-stuffing attempts.
- **Payment security:** Checkout always re-calculates the price from the server's own product catalog
  — a manipulated client request can never change what's actually charged. Payment confirmation is
  independently re-verified against the payment provider's own API before an order is ever marked
  paid; the redirect alone is never trusted.
- **SQL injection:** Every database query in the codebase was checked; all use parameterized queries.
  Zero instances of raw string-built SQL were found.
- **Cross-site scripting (XSS):** Zero instances of unsafe HTML injection were found anywhere in the
  frontend. All AI-generated content (reports, chat replies, plans) is rendered through the standard
  UI framework's automatic escaping.
- **CI/CD security:** The one automated build pipeline that exists has minimally-scoped permissions
  and never runs on untrusted external contributions, so there's no secret-exposure risk there.

---

## 3. Other reliability/performance work done in the same pass

Not a "safety" finding in the AI-governance sense, but relevant to the Technical Product criterion:

- **WhatsApp/chat reply latency reduced.** Every real conversational turn required the AI model to
  make one call just to decide to look up the patient's own data, then a second call to actually
  respond — two sequential AI round-trips minimum for an ordinary question. The backend now looks up
  that data itself before the model is ever invoked, so a normal reply now costs one AI call instead
  of two-plus. Verified this doesn't introduce duplicate database queries or stale data via a direct
  mocked test of the caching behavior.
- **A real cross-browser rendering bug fixed.** Product images on the store page rendered visibly
  warped specifically on Safari/macOS (not Chrome, not Windows) due to a documented WebKit rendering
  interaction between a clipped/rounded image and a nested 3D-transform effect. Fixed by isolating the
  image onto its own rendering layer.

---

## 4. Verification methodology used throughout

Every code change in this pass went through the same discipline before being shipped:

1. **Syntax/compilation check** — every modified Python file was compiled; every modified frontend
   file was checked with the project's build tool for syntax errors.
2. **Full application import** — the entire backend application was imported end-to-end after each
   change to catch any wiring or import-level errors across the whole system, not just the changed
   file.
3. **Targeted logic tests** — for each behavioral change, the specific function(s) involved were
   called directly with constructed inputs and their output checked against explicit expected values
   (not just "it ran without crashing"). This includes: tool-list contents under both old and new
   settings, emergency-phrase detection against both true-positive and true-negative cases, the
   human-oversight escalation logic under both a suppressed-flag/concerning-score scenario and a
   genuinely-low-risk scenario, the admin-access rate-limiter under a simulated repeated-guess
   scenario, and the device-key authentication check under both configured and unconfigured states.

---

## 5. What this pass explicitly did not need to fix

Noted so effort isn't wasted re-investigating these before the evaluation:

- Dependency version pinning (`requirements.txt` uses minimum-version bounds rather than a fully
  locked dependency set) — a reproducibility best-practice gap, not a runtime safety issue, and not
  practically fixable in the time remaining.
- Minor account-enumeration signal on signup (a "this email is already registered" message) — a
  common, widely-accepted tradeoff for signup UX, not worth the engineering time this week.
- No rate limit on two low-sensitivity payment-status read endpoints — low risk given those endpoints
  use long, unguessable identifiers rather than sequential ones.

---

## 6. Known limitations of this validation pass — stated plainly

- **The audit-trail tamper-evidence trigger (§2.7) was not executed against a live database in this
  environment** — no local database server was available to test against. The syntax was written
  using an already-proven pattern from elsewhere in the same file, but this is the one change in this
  entire pass that was verified by code review rather than by execution. **Action item:** confirm
  after deployment that the database migration applied successfully.
- **The device-key authentication (§2.2) is not yet active in production** — it requires a
  coordinated manual step (setting the key on the hosting platform and reflashing the physical
  sensor's firmware with the matching value) that could not be performed remotely.
- **The Safari rendering fix (§3) was diagnosed and fixed from source-code analysis of a known,
  documented browser rendering bug, not from live testing on a physical Mac.** Recommended: confirm
  visually on an actual Mac/Safari before the live demo.
- **This was a code-level audit, not a formal red-team engagement.** It covers the categories listed
  in §1 as they apply to this specific system's architecture, but was performed by AI-assisted code
  review, not by an independent third-party security testing service or a live adversarial red-team
  exercise against the running system.

---

## 7. Traceability — commit history

All changes described above are committed to the `main` branch of the repository and auto-deployed.
In order:

| Commit | Description |
|---|---|
| `f481912` | Pricing update; removed 4 stale pre-hardware planning documents |
| `5d8a6fb` | First hardening pass: device-key auth, autonomous-booking restriction, human-oversight floor fix, emergency gate (WhatsApp), admin rate-limiting |
| `e097e32` | WhatsApp/chat reply-latency fix |
| `6861a76` | Second hardening pass: website chat emergency gate, audit-trail tamper-evidence trigger, safety-page data-processor disclosure |
| `48d4f61` | Safety page rewrite (new mechanism cards, corrected claims) and project documentation update |

Every commit message contains the full technical rationale for that change and can be read directly
from the repository's git history for further detail.
