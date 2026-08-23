# AI Context — Novera

Last updated: 2026-08-23. Read this first in any new session before touching the code — it captures
what's actually built, deployed, and working right now, plus the non-obvious gotchas that cost real
debugging time to find.

## What this project is

Novera is an agentic AI-driven saliva-biosensor platform for non-invasive health screening: a
marketing site + product app (dashboard, AI-written reports, voice readout, self-care coaching,
WhatsApp-based appointment booking), backed by a FastAPI service. Research-stage screening platform,
not a diagnostic device — see `novera-website-build-prompt.md` for the original design/requirements
brief this was built from.

## Getting started on a new machine

The production site/app already work without doing any of this — this is only needed to run the
project **locally** (dev server, local backend) or to make **code changes and redeploy**.

### 1. Prerequisites to install

- **Node.js 22** and npm (frontend build, Capacitor, CI matches this version)
- **Python 3.11+** (backend)
- **Git**
- Not required unless doing local Android native work (CI handles Android builds — see below):
  Android Studio/SDK, JDK 21

### 2. Re-authenticate git (if this came from a zip, not `git clone`)

Credentials live in Windows' credential manager, not in the project folder, so they don't travel
with a zip. First `git push`/`git pull` on a new machine will prompt a GitHub sign-in — normal.

### 3. Recreate the `.env` files — **not** included in the zip/repo (gitignored, contain secrets)

```
backend/.env    — copy from backend/.env.example, then fill in:
                    DATABASE_URL          (a local Postgres, or the Railway one from the dashboard)
                    OPENROUTER_API_KEY    (sk-or-... — from openrouter.ai)
                    META_WHATSAPP_TOKEN / META_PHONE_NUMBER_ID / META_APP_SECRET
                                          (only needed to test the WhatsApp flow locally)

frontend/.env   — copy from frontend/.env.example. Can be left unset for local dev
                   (Vite's dev proxy forwards /api to localhost:8000 instead).
```

None of these secret values are in this doc or the repo — get them from whoever holds them
(Railway dashboard for `DATABASE_URL`, OpenRouter account for the API key, Meta developer console
for WhatsApp).

### 4. Install dependencies and run locally

```
# backend
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
python scripts/init_db.py                                  # creates tables, seeds reference ranges
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# frontend (separate terminal)
cd frontend
npm install
npm run dev              # http://localhost:5173
```

### 5. Deploying changes

Just `git push` to `main` — both Cloudflare (frontend) and Railway (backend) auto-deploy on push,
and the Android APK workflow (`.github/workflows/android-build.yml`) rebuilds automatically for any
push touching `frontend/**`. No manual deploy step exists or is needed.

## Current state — what's live and working

### Frontend — Cloudflare

- **Not classic Cloudflare Pages** — deployed as a **Worker with static assets** (`npx wrangler
  deploy`, triggered by Cloudflare's Git integration on every push to `main`). This distinction
  matters: config lives in `frontend/wrangler.jsonc`, not a Pages-specific dashboard setting.
- Live at `https://www.novera.fun` and `https://novera.fun` (both attached as Custom Domains on the
  Worker) and `https://novera.mohd-abdulmuqtadir2006.workers.dev` (the free `*.workers.dev` URL,
  always active regardless of custom domains). See the 2026-08-23 domain migration entry below —
  `echo-nova.online` is retired, no longer live at all.

### Backend — Railway

- FastAPI + Postgres, live at `https://api.novera.fun` (custom domain on Railway, one-domain-per-
  service plan limit — see the migration entry below for why the old `api.echo-nova.online` had to
  be removed first). Health endpoint `/api/health` confirmed returning `{"ok": true, "db_ok": true, ...}`.
- `scripts/init_db.py` runs as a Railway pre-deploy step (schema + seed data).

### AI models (OpenRouter) — split by stakes

Single `OPENROUTER_API_KEY` covers both — OpenRouter is one gateway, routes by the `model` string
per call:

- `OPENROUTER_MODEL_CONTENT` (default `deepseek/deepseek-chat-v3.1`) — report/voice/self-care/chat
  content agents + WhatsApp intent classification. Cheap, high-volume, lower-stakes.
- `OPENROUTER_MODEL_SCREENING` (default `anthropic/claude-sonnet-5`) — the one organ-screening
  decision call. Higher stakes (feeds `screening_cases`/`confirmed_cases`), worth the extra cost.
- The old free-model auto-discovery logic in `screening_llm.py` was removed when this split landed —
  it's now a fixed configured model, not a dynamically-picked free one.

### Android app (Capacitor)

- `frontend/capacitor.config.json` (appId `online.echonova.novera`) + `frontend/android/` (native
  project, source only — `android/app/build/` and `android/.gradle/` stay gitignored).
- **Built entirely by CI, no local Android Studio/SDK needed anywhere**:
  `.github/workflows/android-build.yml` builds the web app (`VITE_API_URL` pinned to
  `https://api.novera.fun`), runs `npx cap sync android`, builds a **debug** APK via Gradle,
  uploads it as a run artifact, and publishes it to the repo's standing `latest-android-build`
  GitHub Release.
- App icons/splash generated from `frontend/public/logo-mark.png` on the brand's ink background
  (`#080919`) via `@capacitor/assets` — source files in `frontend/assets/`, regenerate with:
  ```
  npx capacitor-assets generate --android --iconBackgroundColor '#080919' --iconBackgroundColorDark '#080919' --splashBackgroundColor '#080919' --splashBackgroundColorDark '#080919'
  ```
- **Debug build only, not Play Store signed** — installing it shows Android's normal "install from
  unknown sources" prompt (one-time per install source, not recurring). Removing that warning
  entirely requires actually publishing to the Play Store ($25 one-time + signed release build +
  store listing) — not done, was explicitly deferred by the user in favor of the free path.
- CORS: the Android WebView calls the API from Capacitor's default virtual origin
  `https://localhost` — already whitelisted in `backend/app/config.py`'s `CORS_ORIGINS` default.

### iPhone — PWA, not a native app

- No Apple Developer account ($99/yr) or Mac needed — the user explicitly chose the free path.
- `vite-plugin-pwa` (configured in `frontend/vite.config.js`) generates the web manifest +
  a Workbox service worker. Precaches the JS/CSS/HTML/icon shell; **deliberately excludes**
  `frames/**` and `frames-mobile/**` (480 hero images total — would bloat install time/storage for
  no benefit, they load fine over the network as the hero scrubs).
- Icons: `frontend/public/pwa-192.png`, `pwa-512.png`, `pwa-maskable-512.png` — same logo mark on
  ink background, generated via a one-off `sharp` script (not a committed script, was run ad hoc;
  regenerate similarly if the logo changes).
- iOS Safari mostly **ignores the web manifest** for "Add to Home Screen" — the meta tags that
  actually drive standalone mode are in `index.html`: `apple-mobile-web-app-capable`,
  `apple-mobile-web-app-status-bar-style`, `apple-mobile-web-app-title`.
- **Hard platform limitation, not a bug**: iOS has no API, URL scheme, or trick to auto-trigger
  "Add to Home Screen" — it's always a manual Share → Add to Home Screen tap. Don't waste time
  trying to work around this later; it's a WebKit restriction, confirmed dead-end.
- `frontend/src/components/ui/IOSInstallBanner.jsx` — detects iOS Safari not already in standalone
  mode, shows a dismissible (sessionStorage, reappears next visit) prompt pointing at Share → Add to
  Home Screen. Bilingual via `install.*` keys in `src/i18n/translations.js`. Mounted globally in
  `App.jsx`.

### Mobile web responsiveness

- **Two hero frame sets**: `frontend/public/frames/` (1280×720 landscape, desktop) and
  `frontend/public/frames-mobile/` (720×1280 portrait, phones — screens ≤767px). Without the
  portrait set, phones were cover-cropping the landscape composition down to a narrow center strip.
  Both are 240 frames, `frame_0001.jpg … frame_0240.jpg`. Switching logic:
  `src/hooks/useScrollFrameSequence.js` → `getFramePath(n, mobile)`.
- Fixed a black-line rendering bug in the same hook's `drawCover`: the canvas is `alpha: false`
  (opaque), so any pixel not covered by the current frame defaulted to pure black instead of the
  page's actual navy (`#080919`) — sub-pixel rounding occasionally left a sliver uncovered, visible
  as a stray line. Now fills with the correct color first and overscans the drawn frame by 1px.
- Scroll-scrub was laggy by design (`scrub: 0.5` in the GSAP ScrollTrigger config = deliberate
  catch-up delay) — changed to `scrub: true` for exact 1:1 tracking. Also added
  `ScrollTrigger.normalizeScroll(true)`, GSAP's documented fix for mobile address-bar-resize jank.
- `overflow-x: hidden` on `html`/`body` (`src/styles/index.css`) — blanket guard against horizontal
  scroll from any source.
- `FloatingOrbs.jsx` orb count now has a floor (`Math.max(45, ...)`) so phone screens don't read as
  sparse relative to desktop's ~90 (orb density scales with screen area).
- **Notch/curved-edge safe areas**: `index.html`'s viewport meta needed `viewport-fit=cover` — without
  it, the page never draws into the safe-area insets at all, and the browser fills that strip with
  its own default grey (this was the "grey lines top and bottom" bug). Added
  `.pt-safe`/`.pb-safe`/`.pl-safe`/`.pr-safe` utility classes (`env(safe-area-inset-*)`) in
  `index.css`, applied to: `Navbar.jsx`'s fixed header, the mobile menu overlay, `PageShell.jsx`'s
  top/bottom content offset, and `FrameScrubHero.jsx`'s bottom-anchored scroll-cue/reduced-motion
  captions.

### "Get Novera" QR page

Published as a Claude Artifact (private by default, share manually if needed) — the QR code encodes
the site URL directly, so it works independent of the artifact's own sharing state. Source:
`.scratch/get-novera.html` (not committed to git — recreate from scratch if needed, it's a
standalone static page). **Stale as of the 2026-08-23 domain migration**: the visible caption/link
text was updated to `www.novera.fun`, but the embedded QR code is a baked PNG that still visually
encodes the old, now-dead `www.echo-nova.online` URL — regenerate the actual QR image (not just the
text) before sharing this page again.

### Autonomous Guidance Agent + live homepage workflow diagram (added 2026-08-14)

The one genuinely agentic capability in the backend (everything else is single-shot "LLM-in-the-loop
structured decisioning"). `backend/app/core/guidance_agent.py` fires as a background task on every
`POST /api/readings` (real ESP32 push or manual) and runs a real tool-calling loop — the model itself
decides which of `run_screening_pipeline` / `generate_report` / `generate_voice_script` /
`generate_self_care_plan` / `offer_clinic_appointment` / `request_retest` to call, in what order, not
a hardcoded sequence. Every step broadcasts over a new public WebSocket (`backend/app/ws.py`,
`/ws/pipeline`) that the homepage's "Live Under the Hood" section (`frontend/src/components/home/
LiveWorkflow/`, replacing the old 3D `AgentFlow3D`) renders as a live n8n-style node diagram —
falls back to a looping preview animation when idle/disconnected so it's never a dead visual.

Hard safety constraints (don't relax these without re-reading why): `offer_clinic_appointment` always
calls `send_offer(..., simulate=True)` hardcoded — the autonomous path can never send a real WhatsApp
message or book a real appointment, only a human-initiated action elsewhere in the app can.
`config.AUTO_AGENT_ENABLED` is a kill switch (Railway env var, default true). A 60s in-memory throttle
prevents overlapping runs. Broadcast payloads carry only step/status/organ-category/coarse-flag/model
labels — never raw biomarker values, patient identity, or free-text notes (it's a public, unauthenticated
socket serving the marketing homepage).

### WhatsApp agent converted to real tool-calling (added 2026-08-14)

`backend/app/core/whatsapp_agent.py` — the real, live, HMAC-verified Meta webhook's brain
(`backend/app/routers/whatsapp.py`'s `POST /webhook`, still untouched) — used to run one
classification call into 5 fixed intent buckets (confirm/decline/reschedule/question/unknown) with
Python branching per bucket. It's now a genuine tool-calling agent, same `bind_tools` loop shape as
`guidance_agent.py` (see below), just synchronous since its caller doesn't await it. Tools:
`get_patient_facts`, `check_slot_availability` (read-only), `book_appointment`, `cancel_appointment`,
`reschedule_appointment`. This did **not** add any new real-world side effect beyond what the handler
already did — replying to the person who just texted, booking/cancelling/rescheduling *their own*
appointment — it only changed how the decision to do so gets made.

Cancel/reschedule are genuinely new capabilities, which needed a schema change: `appointments` gained
a `status` column (`'confirmed'` / `'cancelled'`, never deleted — full audit trail, same ethos as
`decision_audit`), and the old table-wide `UNIQUE(slot_start)` became a partial unique index
(`appointments_slot_start_confirmed_uidx ... WHERE status = 'confirmed'`) so a cancelled slot frees up
for rebooking while the cancelled row stays for history. `booking.find_and_book_slot`'s `ON CONFLICT`
target had to be updated to `ON CONFLICT (slot_start) WHERE status = 'confirmed'` to match the new
partial index as its arbiter. `list_bookings`/`list_upcoming_for_*` now filter to `status = 'confirmed'`
so cancelled rows don't resurface in the Appointments page or the agent's own fact-gathering.

### Screening decision converted to bounded tool-calling (added 2026-08-15)

`screening_llm.decide()` used to be exactly one forced-tool-call OpenRouter invocation. It's now a
small tool-calling loop (`MAX_ITERATIONS = 4`) that can optionally call `get_organ_reference_ranges`
(double-check a specialist result's range_score against the actual configured bands) or
`get_closest_confirmed_cases` (look deeper than the pre-computed top-3 similar cases) before
committing — or call `flag_for_human_review(reason)` instead of forcing a guess on a genuinely
ambiguous case (new `HumanReviewRequested` exception, routed to `scoring.mark_retest_required`, same
status/shape a validation failure already used — zero frontend changes needed).

**Deliberately unchanged, and this is the important part**: all 3 organs are still scored
deterministically by `scoring.py` *before* `decide()` is called — that loop, and both its event
emitters (`process_case_stream`'s SSE `score:{organ}` events for the Appointments page's
`PipelineVisualizer`, and `guidance_agent.py`'s own WS `score_kidney/score_stomach/score_oral`
broadcasts), are byte-for-byte untouched. `decide(reading, specialist_results) -> (decision,
model_name, raw_result)` kept its exact external signature and return contract, so **neither live
integration surface needed a single line changed** — verified live 2026-08-15 via both paths (a
manual "Deep AI analysis" run showing a real evidence-citing reason, and a fresh device reading
lighting up the homepage diagram end to end). A plain-text reply with no tool call is still never
accepted as a valid decision — the no-fabrication guarantee applies exactly as before, just enforced
across a bounded loop instead of a single call. `decision_audit.llm_result_json` now also stores a
`tool_trace` (which investigative tools were called and what they returned) alongside the existing
prediction/confidence/reason.

### Self-care coach converted to real tool-calling (added 2026-08-15)

Two behavior changes, both live-verified: (1) `POST /api/self-care` no longer regenerates the plan
from scratch on every page load — a new single-row `self_care_plan` table persists the last generated
plan, and the request gained a `force` flag (`false` = return the persisted plan instantly, no LLM
call; `true` = regenerate, used by the Dashboard's "Regenerate" button). (2) `POST /api/chat` (the
coach) is now a real tool-calling agent (`content_llm.chat_agent`, same `bind_tools` loop shape as
`guidance_agent.py`/`whatsapp_agent.py`) instead of a single call that regenerated the entire
patient-context blob every turn. Tools: `update_diet_plan_field` (targeted edit to one meal, persisted
to `self_care_plan`), `update_patient_context` (merges into one field of `patient_context`, never
overwrites), `lookup_food_nutrition` (a ~40-food internal dataset — deliberately not an external API,
no new credentials), `check_dietary_conflict` (lightweight rule-based, not another LLM call). Response
gained `planChanged` (additive, alongside the existing `contextChanged`) so the frontend knows to
refresh the plan view after a chat-driven edit. Verified live: asking the coach to swap a meal for a
lower-sodium option produced a real persisted diet-plan edit, not just a chat reply describing one.

### Real AS7341/DHT11 hardware wired in, calibration still unreliable (2026-08-18/19)

Hardware is no longer dummy-mode — see `hardware/esp32_sensor/CALIBRATION_LOG.md` for the full,
still-current story: real sensors are wired in, a channel-mapping firmware bug was found and fixed,
but acid/neutral pH still don't separate on any tried metric and hand-held noise dominates the signal.
`backend/app/core/color_calibration.py` holds the (placeholder) raw-channels-to-value calibration math.

### Sensor stabilization + screening-flag suppression (added 2026-08-20)

Two temporary, config-toggled overrides, both Hassan's explicit call while hardware/calibration catch
up — neither changes stored `combined_score`/calibrated-color data, both are meant to be flipped off
later, not permanent:

- `config.SENSOR_STABILIZATION_ENABLED` (default true): `routers/readings.py` reports every biomarker
  (ph/creatinine/urea, and temperature too, per Hassan) as a tiny drift off the patient's last reading,
  clamped inside the normal reference band, instead of the raw sensor/calibration value. The real
  calibrated color values are still logged for calibration work.
- `config.SUPPRESS_SCREENING_FLAGS` (default true): `scoring.ScoringEngine.evaluate()` forces every
  organ's `flag` to `"low"`, which mutes `whatsapp_gating.enforce_outreach_guarantee`'s forced
  appointment offer. This was on top of a real, separate bug fix in the same file: `_value_fit()` used
  to score any in-range value at 0.85-1.0 (already past the "high" threshold) — a genuinely healthy
  reading was getting forced onto whichever organ it was nearest the center of, at flag=medium/high.
  Rescaled so concern is 0 at a range's midpoint and rises only near/past the edge; verified a mid-normal
  reading now scores ~0.29-0.35 instead of ~0.90+. The flag-suppression override sits on top of that fix,
  not instead of it.

### Report PDF layout fixes (added 2026-08-20)

Both the website's downloaded PDF and the WhatsApp-attached PDF had real layout bugs, fixed separately:
`frontend/src/components/reports/generateReportPdf.js` was slicing one html2canvas screenshot into
fixed-height page chunks with no regard for content boundaries (table rows/text cut in half at page
breaks) — now finds the nearest blank row near each boundary and slices there, with a top margin on
pages after the first. `backend/app/core/report_pdf.py`'s header used a fixed-width single-line
right-aligned headline cell that could overflow into the NOVERA wordmark for a long LLM-generated
headline — now wraps via `multi_cell`; also added a page-break guard around the biomarkers table.

### Store: device + strip-bundle purchase page (added 2026-08-20)

`/buy` (route in `App.jsx`, replacing the old `/subscription` placeholder — `/subscription` now
redirects to `/buy`). One-time purchases only, no subscription of any kind, no referral/hospital-booking
content (out of scope for this page). Pricing lives in exactly one place — `backend/app/core/catalog.py`
— and is load-bearing for the business model; the frontend has zero hardcoded prices, it fetches
`GET /api/catalog`, and checkout always re-prices server-side from the same module, never from client
input. USD prices convert to OMR at the Central Bank of Oman's fixed peg (1 USD = 0.3845 OMR, pegged
since 1986 — see `catalog.py`'s docstring for the source), rounded to whole baisa.

- `frontend/src/pages/Buy.jsx` + `components/buy/{BundleCard,CheckoutForm}.jsx` — device section, the
  3-bundle comparison (Value marked recommended, matching the model's target mix), a `?mode=strips`
  entry point for existing owners (same route, skips device copy, jumps to bundles), and a cart/checkout
  sidebar. Device and every bundle are separate "add to order" line items sharing one cart — decided
  against auto-bundling strips into the device purchase, since a uniform per-product add-to-cart flow is
  simpler and the revenue math is the same either way (see `routers/orders.py`'s `item_type` column).
- `backend/app/routers/orders.py` — `GET /api/catalog` (public), `POST /api/orders/checkout` (public,
  guest checkout allowed — no account required to buy strips), `GET /api/orders/callback` (Thawani's
  redirect target; re-verifies payment status via Thawani's own API before ever marking an order paid —
  never trusts the mere fact of the redirect), `GET /api/orders/{token}` (order status by an opaque
  token, not the sequential id, so orders can't be enumerated).
- `backend/app/core/thawani.py` — hand-rolled Thawani client (no official Python SDK); the REST contract
  was read from Thawani's own open-source WooCommerce plugin source, not guessed. Fails honestly (503,
  nothing charged) via `config.THAWANI_ENABLED` until real `THAWANI_SECRET_KEY`/`THAWANI_PUBLISHABLE_KEY`
  are set — no live merchant credentials exist yet.
- `db/schema.sql`'s `orders`/`order_items` tables: device and bundle line items are never collapsed into
  one SKU even in the same order, tagged `item_type` (`device`/`bundle`) so the financial model can query
  the two revenue lines separately.
- `Navbar.jsx`'s dark/light theme switch was previously keyed only on `pathname === "/"` — extended to
  also treat `/buy` and `/order/:token` as dark-ink pages (they're storefront/marketing pages, not the
  logged-in app's light theme).

### Admin/demo account + WhatsApp trigger (added 2026-08-23)

`config.ADMIN_EMAIL` names a real account (`admin@novera.fun`, created via the live signup API —
`scripts/create_admin_account.py` exists too but SSH into the Railway container hit a persistent
host-key-verification failure from this machine, never resolved) that `core/demo_account.py` keeps
auto-seeded with a synthetic biomarker reading whenever it has none — hooked into
`reference_data.get_latest_row`/`get_reading_history`, the two shared choke points every feature
(dashboard, reports, self-care, voice, screening, WhatsApp) already goes through, so no per-endpoint
changes were needed. Every other account is completely unaffected; the seed only ever fires for this
one configured email and costs nothing when `ADMIN_EMAIL` is unset.

`config.ADMIN_WA_TRIGGER_PHRASE` (currently `"admin login: madaar"`) — sent as the entire text of an
inbound WhatsApp message from ANY phone number, resolves that conversation to the admin account for
24h (in-process only, not persisted across restarts — same accepted-limitation pattern as this file's
other in-memory throttles). A real bearer-secret backdoor by deliberate design (works from any device
for demos); see `whatsapp_agent.py`'s `_try_admin_trigger`/`_admin_session_active`. Verified live: a
correctly-HMAC-signed test webhook payload with that exact phrase produced
`whatsapp_agent: admin trigger recognized` in Railway's logs.

New WhatsApp tool in the same pass: `send_self_care_plan` — WhatsApp previously had no way to deliver
the natural-recovery/self-care plan (diet + area tips) the website's Natural Recovery page already
shows; only report/voice were wired up. Generates-or-reuses the persisted plan, available to any
registered patient with a phone, not just the admin account.

### Domain migration: echo-nova.online → novera.fun (2026-08-23)

`novera.fun` was bought and is now the **only** live domain — `echo-nova.online` is fully retired,
not kept as a working alias. What actually moved, in order:

1. **Cloudflare**: `novera.fun`'s nameservers were already pointed at Cloudflare (same account) but
   attached to a *different*, unrelated Worker (`pulseai`, an old separate project of Hassan's called
   PulseGuard AI) — had to be detached from there first, then attached to the `novera` Worker as
   Custom Domains (`novera.fun` + `www.novera.fun`).
2. **Railway**: the plan allows exactly 1 custom domain per service, and `api.echo-nova.online` was
   already using that slot — had to be deleted before `api.novera.fun` could be added. This produced
   a real (~few minutes) API-down window on the old domain, accepted deliberately by Hassan.
   `api.novera.fun` DNS: a CNAME (`api` → the Railway-provided target) + a `_railway-verify.api` TXT
   record, both added to the `novera.fun` zone, `DNS only` (not proxied) per Railway's requirement for
   its own cert issuance.
3. **Frontend build var**: `VITE_API_URL` (a Cloudflare Worker *build-time* variable — Settings →
   Build → Variables, not a runtime Worker var, since a static-assets Worker can't have those) updated
   to `https://api.novera.fun` and a fresh build manually triggered so the live bundle actually picked
   it up (a plain env-var save does **not** by itself rebuild/redeploy anything).
4. **CORS**: `CORS_ORIGINS` on Railway never had `novera.fun` added when the domain first went live —
   caused a real, user-reported "blocked by CORS policy" login failure. Fixed by updating the env var
   and redeploying; verified via a real preflight (`OPTIONS`) request afterward, not just assumed.
5. **Backend code defaults** (`config.py`'s `SIGNUP_URL`/`PUBLIC_SITE_URL`/`PUBLIC_API_URL`/
   `CORS_ORIGINS` fallback) updated to `novera.fun` — these matter for real, since none of the
   corresponding env vars were ever explicitly set on Railway; the code defaults *are* what's live.
6. **Meta WhatsApp webhook**: callback URL updated to `https://api.novera.fun/webhook` in Meta's own
   dashboard (a manual step outside this codebase — Claude can't log into Meta/Facebook). Verified via
   a real `GET /webhook` 200 in Railway's logs at the moment it was saved.
7. **Physical ESP32 hardware**: `hardware/esp32_sensor/esp32_sensor.ino`'s `API_URL`/`PING_URL` were
   hardcoded to `api.echo-nova.online` — went dead the moment step 2 happened, since editing the
   `.ino` source doesn't affect what's already flashed onto the physical device. Source updated to
   `api.novera.fun`; **still needs a real re-flash of the physical device** (Hassan's own action,
   outside anything Claude can do remotely) before the sensor can submit readings again.
8. **`.scratch/get-novera.html`** (untracked, not part of git): caption/link text updated to
   `www.novera.fun`, but the embedded QR code is a baked PNG still visually encoding the old, now-dead
   URL — the image itself needs regenerating, not just the text, before this page is shared again.

## Key files / architecture

- `backend/app/main.py` — FastAPI entry; routers in `backend/app/routers/`.
- `backend/app/core/scoring.py` — the deterministic organ-scoring math (range score + similarity
  score), untouched by the agentic conversion below. **No trained ML model** — deliberate.
- `backend/app/core/screening_llm.py` (`decide()` converted 2026-08-15) — all 3 organs are still
  scored deterministically *before* `decide()` is ever called (unchanged); `decide()` itself is now a
  small bounded tool-calling loop (`get_organ_reference_ranges`, `get_closest_confirmed_cases`,
  `flag_for_human_review`, `FinalDecision`) instead of one forced call — see the dated section below
  for the full design and why its external contract deliberately never changed.
- `backend/app/core/content_llm.py` — LLM client for report/voice/self-care/chat, uses
  `OPENROUTER_MODEL_CONTENT`. `report_agent` has an optional `get_reading_history` tool (trend
  awareness). The self-care chat coach (`chat_agent`, converted 2026-08-15) is a real tool-calling
  agent — see the dated section below.
- `backend/app/core/fallbacks.py` — deterministic bilingual fallback for every AI call except the
  screening decision (which releases the case back to `NEW` with no invented result if OpenRouter
  fails, rather than fabricating a fallback answer).
- `backend/app/core/whatsapp_agent.py` (converted 2026-08-14) — the real Meta webhook's brain, now a
  genuine tool-calling agent (`ChatOpenAI(...).bind_tools([...])`, same manual invoke -> tool_calls ->
  ToolMessage -> invoke loop shape as `guidance_agent.py`, just synchronous). The model itself decides
  which of `get_patient_facts` / `check_slot_availability` / `book_appointment` / `cancel_appointment`
  / `reschedule_appointment` to call and in what order — no more fixed 5-bucket intent classification.
  Every write tool still goes through `core/booking.py` (Postgres, no LLM in the write path itself,
  can't be double-booked — the partial unique index on `appointments(slot_start) WHERE status =
  'confirmed'` is what makes a cancelled slot reusable while keeping the cancelled row for history).
  `MAX_ITERATIONS = 5`; any failure (AI disabled, an exception mid-loop, hitting the cap with no final
  text) degrades to a deterministic fact-grounded fallback, never leaves an inbound message unanswered.
- `backend/app/core/appointment_graph.py` — **unrelated, separate, deliberately untouched**: the
  simple LangGraph intent-classify-then-book simulator behind `POST /api/appointment/reply`, used only
  by the Appointments page's manual reply box in the dashboard. Not the real WhatsApp webhook path.
- `backend/app/core/guidance_agent.py` + `backend/app/ws.py` — the other real tool-calling agent (see
  "Autonomous Guidance Agent" above) — fires on every reading instead of every inbound WhatsApp
  message, but same bind_tools loop pattern that `whatsapp_agent.py` now also follows.
- `frontend/src/pages/` — one file per route.
- `frontend/src/hooks/useScrollFrameSequence.js` — GSAP scroll-scrub hero logic (desktop + mobile
  frame sets).
- `hardware/esp32_sensor/` — wireless ESP32 sketch that POSTs straight to `POST /api/readings` over
  WiFi (no laptop/browser in the loop). Currently sends dummy randomized values in the dashboard's
  reference bands — no sensors wired up yet; see that folder's README for how to swap in real
  sensor reads later. Needed zero backend/frontend changes since `/api/readings` already accepts a
  partial JSON body. Supports multiple WiFi networks (`WiFiMulti`, e.g. home + phone hotspot — add
  as many `WIFI_SSID_n`/`WIFI_PASSWORD_n` pairs as needed).
- **Device status + on-demand sampling** — `backend/app/routers/device.py` + `device_state` table
  (single row, `db/schema.sql`). The ESP32 heartbeats `POST /api/device/ping` every 3s with its
  SSID; the Dashboard polls `GET /api/device/status` every 5s to show connected/offline + SSID
  (`frontend/src/components/dashboard/DeviceStatusBadge.jsx`, `useDeviceStatus` hook) — "online" is
  inferred purely from how recently a ping landed (15s window), no persistent connection. The
  Dashboard's **Take New Sample** button (renamed from "Simulate new sample") calls
  `POST /api/device/request-sample` to set a pending flag, then polls `GET /api/readings/latest`
  for a newer timestamp (30s timeout, shows `dash.sampleTimeout` on failure) instead of fabricating
  a value itself. The ESP32 sees the pending flag on its next ping and takes a real reading
  immediately; `POST /api/readings` clears the flag on insert either way.

## Constraints and gotchas (hard-won, don't rediscover these)

- **Never hardcode secrets** — everything from env vars (`backend/app/config.py`,
  `frontend/.env`/`VITE_*`). `.env` gitignored, `.env.example` holds placeholders only.
- **Screening pipeline is intentionally not ML** — don't reach for scikit-learn/XGBoost/`.pkl` here.
- **`public/_redirects` breaks the Cloudflare Worker deploy** — conflicts with `wrangler.jsonc`'s
  `not_found_handling: "single-page-application"` and gets rejected with an "infinite loop" error.
  Don't re-add it; the wrangler config already handles SPA routing fallback.
- **`gradlew` needs its executable bit** — git on Windows strips it on commit, causing
  `Permission denied` (exit 126) in the GitHub Actions Android build. Already fixed
  (`git update-index --chmod=+x` + a defensive `chmod +x` in the workflow), but if `android/gradlew`
  ever gets re-committed from a Windows checkout, check this again.
- **Capacitor 8 needs JDK 21**, not 17 — `capacitor.build.gradle` sets
  `sourceCompatibility/targetCompatibility` to `VERSION_21`. The workflow's `setup-java` step is
  pinned to 21 for this reason.
- **GitHub Actions `GITHUB_TOKEN` is read-only by default on this repo** — the Android workflow has
  explicit `permissions: contents: write` so `softprops/action-gh-release` can create/update the
  `latest-android-build` release. Without it, the release-publish step 403s even though the APK
  build itself succeeds.
- **Re-running a failed GitHub Actions run reuses the *original* commit**, not the latest push — if
  a workflow fix doesn't seem to take effect, check whether "Re-run failed jobs" was used (wrong)
  vs. triggering a fresh run via `workflow_dispatch` or a new push (right).
- **The PWA service worker serves stale JS after a deploy, even to a hard-reload** — found 2026-08-14
  verifying a frontend push live. `vite-plugin-pwa`'s `registerType: "autoUpdate"` does *not* mean a
  browser tab that already has the app installed/visited picks up new code on its next load — Cloudflare
  can have the new build live (confirmed by curling the deployed JS chunk directly) while the browser
  still renders the previous version from the old service worker's cache. Fix: in DevTools console (or
  via the `javascript_tool`), `(await navigator.serviceWorker.getRegistrations()).forEach(r =>
  r.unregister())` + `(await caches.keys()).forEach(k => caches.delete(k))`, then reload. Don't waste
  time re-checking the deploy itself once you've confirmed the server-side asset is already correct —
  the staleness is client-side.
- Meta WhatsApp only allows free-form replies within 24h of the user's last message.
- Case confirmation (building the similarity-scoring memory) is CLI-only —
  `backend/scripts/screening_cli.py confirm`, no UI.
- **Railway's GitHub auto-deploy can silently stop working two independent ways** — found 2026-08-10
  when pushes stopped deploying with no error surfaced anywhere in git/GitHub: (1) the Railway
  GitHub App itself had been fully uninstalled from the GitHub account (invisible from Railway's
  side — its Settings → Source still showed the repo name, just with a red "GitHub Repo not found"
  underneath; confirm via `github.com/settings/installations` on the GitHub side, not Railway's UI),
  and (2) independently, the "Auto deploys when pushed to GitHub" toggle on the branch connection
  (Settings → Source → "Branch connected to production") was switched off. Both had to be fixed —
  reinstalling the GitHub App alone wasn't enough. If a push doesn't deploy, check both, and don't
  assume a stuck build means the Nixpacks/Docker build itself is broken. `railway up --detach` from
  the repo root (not `backend/` — the CLI resolves the configured `/backend` root directory relative
  to wherever it's invoked, and running it from inside `backend/` fails with "Failed to read app
  source directory") is the manual-deploy escape hatch while auto-deploy is down.

## Open / deferred

- **RAG for the self-care coach**: discussed but *not implemented* — Novera currently has no large
  document corpus to search (WhatsApp/self-care Q&A answers from a patient's own small structured
  Postgres record, which is a lookup, not a search problem). Only becomes relevant if a real
  medical/nutrition reference corpus gets built for grounding self-care advice — and even then,
  start with plain semantic search before reaching for hybrid search + cross-encoder reranking +
  query rewriting + a formal IR eval harness (that level of sophistication suits corpora in the
  thousands-of-documents range, not a starting corpus of a few dozen/hundred docs).
- **Android Play Store publishing** — not done; app is a sideloaded debug APK only.
- **iOS native app** (Capacitor iOS + Xcode via a macOS CI runner) — not set up; PWA was the chosen
  path instead, per explicit cost tradeoff discussion.
- **No automated tests** anywhere (backend or frontend). CI currently only builds the Android APK,
  doesn't run any test suite.
- **Thawani not actually live yet** — `/buy` checkout is real, working code (see "Store" section
  above) but `THAWANI_SECRET_KEY`/`THAWANI_PUBLISHABLE_KEY` aren't set anywhere yet, so checkout
  currently 503s honestly rather than charging anyone. Needs real Thawani merchant credentials
  (thawani.om) before it can take a real payment — register, then set both env vars on Railway (and
  flip `THAWANI_ENV=production` once past UAT testing).
- **`SENSOR_STABILIZATION_ENABLED`/`SUPPRESS_SCREENING_FLAGS`** (both default true, `config.py`) —
  temporary overrides pending better hardware/calibration, meant to be flipped off deliberately later,
  not permanent product decisions. See the dated section above before assuming either is still needed.

## Related knowledge base notes

None yet in the main Knowledge Base vault. This project's business/pitch materials (financial study,
investor proposal, pitch deck) live in a separate vault at `Desktop/AI Projects/novera/Novera`, out
of scope for the main Knowledge Base unless asked.
