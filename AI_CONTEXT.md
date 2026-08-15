# AI Context — Novera

Last updated: 2026-08-14. Read this first in any new session before touching the code — it captures
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
- Live at `https://www.echo-nova.online` and `https://echo-nova.online` (both attached as Custom
  Domains on the Worker) and `https://novera.mohd-abdulmuqtadir2006.workers.dev` (the free
  `*.workers.dev` URL, always active regardless of custom domains).
- DNS: `echo-nova.online` was originally on IONOS, nameservers now point to Cloudflare
  (`rob.ns.cloudflare.com` / `harleigh.ns.cloudflare.com`) — confirmed propagated. Old IONOS-era A
  records (pointing at a former Vercel deployment, IP `216.198.79.1`) had to be deleted from
  Cloudflare's own DNS records (they'd been auto-imported on initial domain add) before the Custom
  Domain feature would attach `www` and the apex.

### Backend — Railway

- FastAPI + Postgres, live at `https://api.echo-nova.online` (custom domain on Railway). Health
  endpoint `/api/health` confirmed returning `{"ok": true, "db_ok": true, ...}`.
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
  `https://api.echo-nova.online`), runs `npx cap sync android`, builds a **debug** APK via Gradle,
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
`https://www.echo-nova.online` directly, so it works independent of the artifact's own sharing
state. Source: `.scratch/get-novera.html` (not committed to git — recreate from scratch if needed,
it's a standalone static page).

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

## Key files / architecture

- `backend/app/main.py` — FastAPI entry; routers in `backend/app/routers/`.
- `backend/app/core/scoring.py`, `screening_llm.py` — the screening pipeline: reference-range score +
  similarity score + exactly one OpenRouter decision call. **No trained ML model** — deliberate.
- `backend/app/core/content_llm.py` — shared LLM client for report/voice/self-care/chat, uses
  `OPENROUTER_MODEL_CONTENT`.
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
- **`echo-nova.online` (bare apex) custom domain** — was being attached in parallel with `www`;
  verify it's still resolving correctly in a fresh check before assuming it's stable, since this was
  mid-troubleshooting when last touched.

## Related knowledge base notes

None yet in the main Knowledge Base vault. This project's business/pitch materials (financial study,
investor proposal, pitch deck) live in a separate vault at `Desktop/AI Projects/novera/Novera`, out
of scope for the main Knowledge Base unless asked.
