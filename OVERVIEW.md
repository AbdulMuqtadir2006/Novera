# Novera — Project Overview

A complete explainer of what Novera is, what's actually built and live, and where things stand —
for anyone picking up the project cold. (For day-to-day dev/session reference — the authoritative,
constantly-updated source — see `AI_CONTEXT.md`; for backend specifics see `backend/README.md`; for
frontend specifics see `frontend/README.md`; for the AI-safety audit see
`VALIDATION_AND_TESTING_REPORT.md`. This file is the "explain the whole thing" document.)

---

## 1. What Novera is

Novera is an **agentic AI-driven saliva-biosensor platform for non-invasive health screening**:

> A patient provides a saliva sample to a physical sensor device → biomarkers (pH, creatinine,
> urea, temperature) are read → an AI pipeline screens for early signs of concern across three
> organ systems (**kidney, liver, oral**) → the patient gets a dashboard, an AI-written report, a
> voice readout, self-care coaching, and — where warranted — a WhatsApp-based path to book a real
> clinic appointment.

It is explicitly framed throughout the product as a **research-stage screening platform, not a
diagnostic device** — that line appears in both READMEs and on the site's `/safety` page.

**Built for a real, named competition:** Oman's Ministry of Transport, Communications and IT
*"Engineer it with AI"* competition (`AI Competition Evaluation Criteria.pdf` in the repo root),
scored Impact 25% / Technical Product 25% / Relevance & Innovation 20% / AI Safety & Oversight 15%
/ Team & Future Plans 10% / Pitch Quality 5%. The **Final Evaluation was 2026-08-30/31** — already
in the past as of this writing (today is 2026-09-18) — and a two-round AI safety/security hardening
pass (§8 below) was completed 2026-08-25/26 specifically ahead of it.

Business/pitch materials (financial study, investor proposal, pitch deck) live in a **separate**
Obsidian vault at `Desktop/AI Projects/novera/Novera` — out of scope here.

---

## 2. Live today

| Layer | Where | Status |
|---|---|---|
| Frontend | `https://www.novera.fun` / `https://novera.fun` (Cloudflare Worker + static assets, custom domains) + `https://novera.mohd-abdulmuqtadir2006.workers.dev` (always-on free URL) | Live |
| Backend | `https://api.novera.fun` (Railway, FastAPI + Postgres) | Live, `/api/health` confirmed |
| Android | Sideloaded debug APK, auto-built by CI, published to the repo's `latest-android-build` GitHub Release | Live, not Play Store |
| iOS | PWA (Add to Home Screen) — no native app | Live |
| WhatsApp | Meta Cloud API, real HMAC-verified webhook | Live, but see §9 (shared-number pause switch) |
| Checkout (`/buy`) | Real code path, Thawani payment gateway | Working end-to-end **except** it 503s honestly — no live Thawani merchant credentials yet |

Deploys are fully automatic: `git push` to `main` triggers Cloudflare (frontend) and Railway
(backend) simultaneously; any push touching `frontend/**` also kicks off the Android APK build.
There is no manual deploy step in the normal workflow.

---

## 3. Product features (what a user actually sees)

| Route | What it does |
|---|---|
| `/` | Frame-scrub hero (240-frame GSAP scroll animation, separate desktop/mobile frame sets), agent pipeline explainer, health areas, how-it-works, a **live "Under the Hood" workflow diagram** that shows the autonomous agent actually running in real time (or a looping preview when idle), CTA. |
| `/dashboard` | Live readings, metric cards + sparklines, screening gauge, trend charts. "Take New Sample" triggers a real on-demand device reading (not a fabricated value). |
| `/reports` | AI-written bilingual (EN/AR) screening report, regenerated per sample, downloadable as a bilingual PDF. |
| `/voice` | AI-written voice script, read aloud via the Web Speech API. |
| `/self-care` | AI diet plan + per-area guidance, plus a coach chatbot that can edit the plan and remember doctor context — a real tool-calling agent, not a stateless Q&A box. |
| `/more` | Appointments — WhatsApp booking simulator, deep organ-screening analysis, clinic info, bookings list. |
| `/buy` | Device + strip-bundle purchase page — one-time purchases only, no subscription. |
| `/safety` | Public disclosure page describing the actual safety mechanisms running in production (kept honest — see §8). |

Every route is bilingual (EN/AR) with a navbar language toggle persisted in `localStorage`; Arabic
flips the document to RTL and switches to the Cairo font.

---

## 4. Architecture

```
Browser (React 18 + Vite, Cloudflare Worker w/ static assets)
   │  VITE_API_URL  (or Vite dev proxy → localhost:8000)
   ▼
FastAPI (Railway)                              Postgres (Railway)
   ├── auth, readings, patient context ───────► readings, patient_context, chat_messages, users, sessions
   ├── content agents (OpenRouter)             ── report / voice / self-care / chat
   ├── screening pipeline (deterministic        ── screening_cases, confirmed_cases, decision_audit
   │    scoring + one bounded OpenRouter call)
   └── Meta WhatsApp Cloud API webhook ────────► appointments
         └── real tool-calling agent (same bind_tools loop shape used everywhere else)
```

**Frontend:** React 18, Vite, Tailwind, Framer Motion, GSAP (the frame-scrub hero), Recharts,
lucide-react, jsPDF + html2canvas (bilingual PDF export), Web Speech API. Deployed as a Cloudflare
**Worker with static assets** (`wrangler.jsonc`) — not classic Cloudflare Pages, a distinction that
matters for where config lives.

**Backend:** FastAPI + Postgres on Railway. Replaces an earlier Node/Express + separate Python AI
service architecture. Every AI call has a deterministic bilingual fallback (`core/fallbacks.py`) so
the app stays functional with no OpenRouter key or if OpenRouter is down — the one deliberate
exception is the screening decision itself, which releases a case back to `NEW` with no invented
result rather than fabricate a fallback prediction.

**AI models (OpenRouter, one gateway, two tiers by stakes):**
- `OPENROUTER_MODEL_CONTENT` (default `deepseek/deepseek-chat-v3.1`) — report/voice/self-care/chat
  content generation + WhatsApp intent work. Cheap, high-volume.
- `OPENROUTER_MODEL_SCREENING` (default `anthropic/claude-sonnet-5`) — the one organ-screening
  decision call. Higher stakes, worth the extra cost.

---

## 5. The screening pipeline — deliberately not ML

`backend/app/core/scoring.py` computes a deterministic **range score + similarity score** for each
of three organs (**KIDNEY, LIVER, ORAL**) from the raw biomarkers — **no trained model, no
scikit-learn/XGBoost, no `.pkl` file anywhere.** That scoring is untouched by everything below it.

`screening_llm.decide()` is the one place an LLM enters the screening decision: a small **bounded
tool-calling loop** (max 4 iterations) that can optionally call `get_organ_reference_ranges` or
`get_closest_confirmed_cases` before committing, or call `flag_for_human_review(reason)` instead of
forcing a guess on a genuinely ambiguous case. A plain-text reply with no tool call is never
accepted as a valid decision. `decision_audit` stores the full `tool_trace` alongside the
prediction/confidence/reason, and — as of the safety hardening pass — is **DB-enforced append-only**
via a Postgres trigger, not just an application convention.

Case confirmation (building the similarity-scoring memory) is **CLI-only**:
`backend/scripts/screening_cli.py confirm --case-id N151 --organ KIDNEY --confirmed-by "Dr. Amal"` —
there is no UI for this.

---

## 6. The agentic layer — four real tool-calling agents, one loop shape

All four use the same manual `bind_tools` → invoke → tool_calls → ToolMessage → invoke loop pattern:

1. **`guidance_agent.py`** — the "Autonomous Guidance Agent." Fires as a background task on every
   `POST /api/readings` (real device push or manual) and genuinely decides which of
   `run_screening_pipeline` / `generate_report` / `generate_voice_script` /
   `generate_self_care_plan` / `offer_clinic_appointment` / `request_retest` to call and in what
   order. Broadcasts every step over a public WebSocket (`/ws/pipeline`) that drives the homepage's
   live workflow diagram. **Hard safety constraint:** `offer_clinic_appointment` always simulates —
   this path can never send a real WhatsApp message or book a real appointment.
2. **`whatsapp_agent.py`** — the real Meta webhook's brain. Decides which of `get_patient_facts`,
   `check_slot_availability`, `book_appointment`, `cancel_appointment`, `reschedule_appointment` to
   call. **Autonomous/proactive triggers (wellness check-ins, sensor-reading triggers) cannot book,
   cancel, or reschedule** — only a patient's own reactive reply can commit a real booking
   (`allow_booking=False` hardcoded on the autonomous entry point, added in the safety pass).
3. **`screening_llm.decide()`** — see §5.
4. **Self-care coach (`content_llm.chat_agent`)** — can call `update_diet_plan_field`,
   `update_patient_context`, `lookup_food_nutrition` (a small internal dataset, deliberately not an
   external API), `check_dietary_conflict`.

All appointment writes (from any agent) still go through `core/booking.py` — Postgres-only, no LLM
in the write path, can't double-book (a partial unique index on `appointments(slot_start) WHERE
status = 'confirmed'` lets a cancelled slot be rebooked while keeping the cancelled row for audit
history).

**Deterministic emergency gate:** `backend/app/core/emergency.py` — a non-LLM keyword check (chest
pain, can't breathe, suicidal ideation, etc., EN+AR) shared by both the website chat and WhatsApp,
short-circuiting straight to "call 9999 / go to the ER" before any model call happens.

---

## 7. Hardware

`hardware/esp32_sensor/` — an ESP32 sketch that POSTs directly to `POST /api/readings` over WiFi
(supports multiple saved networks via `WiFiMulti`). Real AS7341 (color/spectral) + DHT11
(temperature) sensors are wired in as of 2026-08-18/19 — **no longer dummy-mode** — but calibration
is still unreliable: acid/neutral pH don't cleanly separate on any tried metric yet, and hand-held
noise dominates the signal (`hardware/esp32_sensor/CALIBRATION_LOG.md` has the full story).

Two temporary, explicitly-config-toggled overrides sit in front of the raw calibration while
hardware work continues (`config.SENSOR_STABILIZATION_ENABLED`, `config.SUPPRESS_SCREENING_FLAGS`,
both default `true`) — they affect what's *displayed*, not the real logged calibration data or the
underlying safety floor (see §8's human-oversight fix for why those are no longer the same thing).

**Device status + on-demand sampling:** the ESP32 heartbeats `POST /api/device/ping` every 3s; the
dashboard polls `GET /api/device/status` every 5s and infers online/offline purely from ping
recency. "Take New Sample" sets a pending flag the device picks up on its next ping and answers with
a real reading — not a fabricated one.

**Device authentication:** `X-Device-Key` support was added to `POST /api/readings` and
`POST /device/ping` in the safety pass, but is a **deliberate no-op today** — the key is unset on
both Railway and the physical device's firmware. Needs both sides updated together (Railway env var
+ ESP32 reflash) or the real device gets locked out.

---

## 8. AI safety & security hardening pass (2026-08-25/26)

A real, code-level audit done specifically for the competition's "AI Safety & Oversight" (15%)
category, ahead of the 2026-08-30/31 Final Evaluation. Full detail in
`VALIDATION_AND_TESTING_REPORT.md`; summary:

| Category | Result |
|---|---|
| Tool-calling safety / authorization | 1 finding, fixed (autonomous booking removed) |
| Privacy / data-leakage | 1 finding, fixed (device auth added) + 1 disclosure gap, fixed |
| Medical-response safety | 2 findings, fixed (emergency gate added to both surfaces) |
| Agentic autonomy | 1 finding, fixed |
| Human oversight | 1 finding, fixed (outreach guarantee was silently dead — see below) |
| Auditability | 1 finding, fixed (DB-enforced append-only audit trail) |
| Prompt injection, hallucination, reliability, web auth, payment security, SQLi, XSS, CI/CD | Reviewed — already solid |

**The one finding worth understanding in detail:** the human-oversight "safety floor"
(`whatsapp_gating.enforce_outreach_guarantee`, meant to force a human-reachable outreach for a
genuinely concerning reading) used to key off the patient-facing `flag`, which
`SUPPRESS_SCREENING_FLAGS=true` forces to `"low"` for every case for calibration reasons — so the
safety floor **never actually fired in production**. It now also checks the real, never-suppressed
`combined_score` directly, so a concerning reading still reaches a human even while the displayed
flag stays calm. The `/safety` page's own standing promise is that every mechanism described there
is grounded in code actually running in production — which is why the device-key fix above is
deliberately **not** listed there yet (it isn't enforced until the Railway+reflash step happens).

Four stale business-facing docs (`TEAM_AND_ROADMAP.md`, `DATA_PRIVACY_AND_SAFETY.md`,
`REGULATORY_AND_CLINICAL_PATHWAY.md`, `PITCH_ADDENDUM.md`) were deleted in this same pass for being
out of date with the shipped code — still recoverable from git history if needed.

---

## 9. WhatsApp — shared number, pause switch

The Meta WhatsApp Business number is **shared with a separate, unrelated project (AmnTech**, an
industrial-safety wearable whose own WhatsApp alerting is a completely separate process on another
machine and doesn't touch this backend). `config.NOVERA_WHATSAPP_PAUSED` (env var, default `false`)
was added 2026-09-15 as a one-flag kill switch for all Novera-initiated WhatsApp traffic, for when
the number needs to be free for AmnTech — pauses sends and inbound processing alike, no code changes
needed to resume.

Also fixed the same period: a duplicate-message bug (several tools message the patient directly as
a side effect *and* were also being relayed as a reply — fixed in two separate code paths that had
the same underlying issue) and voice notes, which now genuinely synthesize speech (gTTS, no API
key/ffmpeg needed) instead of sending the script as plain text.

---

## 10. Store / checkout

`/buy` — device + 3 strip bundles (Starter/Value/Pro), one-time purchases only, no subscriptions.
Pricing lives in exactly one place (`backend/app/core/catalog.py`) and is load-bearing for the
business model — the frontend has zero hardcoded prices, always fetches `GET /api/catalog`, and
checkout always re-prices server-side. USD converts to OMR at the Central Bank of Oman's fixed peg
(1 USD = 0.3845 OMR). Bundle pricing was deliberately dropped to $3/$6/$13 (from $27/$58/$98) as a
confirmed loss-leader strategy, even below COGS.

Checkout goes through a hand-rolled **Thawani** client (no official Python SDK — the REST contract
was read from Thawani's own open-source WooCommerce plugin). **Not live yet**: no real
`THAWANI_SECRET_KEY`/`THAWANI_PUBLISHABLE_KEY` are set anywhere, so checkout currently fails
honestly (503, nothing charged) rather than pretending to work.

---

## 11. Domain history

`novera.fun` is the current and only live domain. The project originally launched on
`echo-nova.online`, fully migrated 2026-08-23 (Cloudflare Worker custom domains, Railway's
one-custom-domain-per-service limit required deleting the old domain first, `VITE_API_URL` rebuilt,
`CORS_ORIGINS` updated, Meta's webhook callback URL updated, and the physical ESP32 firmware
re-flashed with the new API host). `echo-nova.online` is fully retired, not kept as a working alias.

---

## 12. Mobile

- **Android:** wrapped via Capacitor (`appId online.echonova.novera`). Built **entirely by CI** — no
  local Android Studio/SDK needed. Produces a **debug** APK only, sideloaded (not Play Store
  signed); Play Store publishing ($25 + signed release + store listing) was explicitly deferred by
  the user in favor of the free path.
- **iOS:** no native app — a **PWA** instead (no $99/yr Apple Developer account or Mac needed, an
  explicit cost tradeoff). `vite-plugin-pwa` + a Workbox service worker; iOS Safari's "Add to Home
  Screen" is always a manual Share-menu tap (a confirmed hard WebKit limitation, not a bug to keep
  chasing).

---

## 13. Open / deferred

- **RAG for the self-care coach** — discussed, not implemented; there's currently no large document
  corpus to search (patient Q&A is a small structured-record lookup, not a search problem). Only
  relevant if a real medical/nutrition reference corpus gets built later.
- **Android Play Store publishing** — not done, sideloaded debug APK only.
- **iOS native app** — not planned; PWA was the deliberate chosen path.
- **No automated tests** anywhere (backend or frontend); CI only builds the Android APK.
- **Thawani payments** — real working code path, but not live (no merchant credentials yet).
- **`SENSOR_STABILIZATION_ENABLED`/`SUPPRESS_SCREENING_FLAGS`** — temporary display-layer overrides
  pending better hardware/calibration, meant to be turned off later, not permanent.
- **Device-key auth** (`DEVICE_API_KEY`) — shipped but not enforced; needs a coordinated Railway env
  var + ESP32 reflash.

---

## 14. Quick facts

- **Location:** `Desktop\Novera`
- **GitHub:** `AbdulMuqtadir2006/Novera`
- **Live site:** `https://www.novera.fun`
- **Live API:** `https://api.novera.fun`
- **Frontend:** React 18 + Vite + Tailwind + Framer Motion + GSAP, Cloudflare Worker (static assets)
- **Backend:** FastAPI + Postgres, Railway
- **AI:** OpenRouter (DeepSeek for content, Claude Sonnet 5 for the screening decision)
- **Screening:** deterministic scoring (no ML model) + one bounded LLM decision call, 3 organs
- **Context:** built for Oman's "Engineer it with AI" government competition; Final Evaluation was
  2026-08-30/31
