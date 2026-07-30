# Novera — Website & AI Product App

Marketing site + full-stack product app for **Novera**, an agentic AI-driven
saliva biosensor platform for non-invasive health screening. A single saliva
sample flows into a real SQLite database; a Claude-powered agent layer turns each
reading into a screening report, a spoken summary, and a personalised diet /
self-care plan — in **English or Arabic**.

## Architecture

```
Browser (React + Vite)
   │  /api/*  (Vite dev proxy → :3001)
   ▼
Express API  (server/)               node:sqlite → novera.db
   │  delegates all AI over HTTP     (readings, patient_context, chat_messages)
   ▼
Python agentic service (../Novera ai part, FastAPI :8000)
   ├── LangGraph agents → OpenRouter (free)   [report · voice · self-care · chat · organ]
   └── Meta WhatsApp Cloud API (WhatsApp appointment agent)
```

The AI now runs in the **Python LangGraph service** (`../Novera ai part`) on
OpenRouter, not in Node. The Node backend proxies to it (`AI_SERVICE_URL`, default
`http://127.0.0.1:8000`) and falls back to deterministic bilingual output if the
service is down. See that folder's README for the agents + WhatsApp go-live steps.

- **Frontend:** React 18, Vite, Tailwind, Framer Motion, GSAP (frame-scrub hero),
  Recharts, lucide-react, jsPDF + html2canvas (bilingual PDF), Web Speech API.
- **Backend:** Node + Express + built-in `node:sqlite` (no native build), the
  Anthropic SDK.
- **AI:** every AI call has a deterministic **bilingual fallback**, so the app is
  fully functional even with no API key or no credits.

## Run it

Three services — start them in this order:

```bash
# 1) Python AI service  (from ../Novera ai part)
cd "../Novera ai part"
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m uvicorn api:app --host 127.0.0.1 --port 8000

# 2) Node backend  (from novera-web/) — seeds ~30 readings, API on :3001
npm run server:install
npm run server:seed
npm run server

# 3) Frontend
npm install
npm run dev            # http://localhost:5173 (or next free port)
```

The app works even if the Python service is down (deterministic fallbacks), but
you need it running for real AI output and the WhatsApp appointment flow.

`npm run build` produces the production frontend in `dist/`.
`cd server && npm run seed -- --force` reseeds the database.

## Claude API key

The AI layer reads `ANTHROPIC_API_KEY` from `server/.env` (gitignored):

```
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-opus-5
PORT=3001
```

- **No key / no credits →** the backend logs the reason and serves the
  deterministic EN/AR fallback (`"source":"fallback"` in responses, an "Offline
  summary" badge in the UI). Nothing breaks.
- **Valid key + credits →** real Claude output appears automatically, no code
  change. Add credits at console.anthropic.com → Plans & Billing.

> ⚠️ Rotate any key that has been shared in plaintext.

## Features

| Route | What it does |
|---|---|
| `/` | Frame-scrub hero, agents pipeline, health areas, how-it-works, CTA. Nav is transparent over the dark page. |
| `/dashboard` | Live readings from SQLite. **Most-recent value** banner on top, metric cards + sparklines, screening gauge, trend charts (7/30/all). **Simulate new sample** adds a row to the DB — voice/report/self-care all update from it. |
| `/reports` | AI-written screening report (EN/AR), regenerated per sample. Bilingual PDF via html2canvas snapshot (correct Arabic shaping). |
| `/voice` | AI voice script read aloud via Web Speech API; picks an Arabic system voice in AR. Live transcript + orb synced to speech events. |
| `/self-care` | AI diet plan + per-area guidance from the latest reading, **plus a coach chatbot**: tell it what your doctor said (diagnosis / meds), it stores that context in the DB and regenerates the plan around it. |
| `/more` | **Appointments** — agentic WhatsApp booking: send the offer, reply as the patient (local simulator), and the LangGraph agent books at Badr Al Samaa with a Maps link. Also "Deep AI analysis" (organ prediction) + clinic + bookings list. |

## Bilingual (EN / AR)

- Language toggle in the navbar; choice persists in `localStorage`.
- Arabic switches the document to **RTL** and the Cairo font across all type roles.
- UI strings live in `src/i18n/translations.js`; AI content is generated in the
  selected language by the backend.

## Data layer

`node:sqlite` database at `server/novera.db`:

- `readings` — biomarker rows (pH, creatinine, urea, temperature) + timestamp.
- `patient_context` — doctor diagnosis / medications / notes (updated by the chatbot).
- `chat_messages` — the coach conversation.

Status and health-area logic lives in `server/health.js` (single source of truth).

## Frame sequence

The 240 hero frames are in `public/frames/` as `frame_0001.jpg … frame_0240.jpg`
(1280×720). Scrub logic: `src/hooks/useScrollFrameSequence.js` — GSAP pin + scrub,
cover-fit, DPR-aware, preloads with a progress bar, samples every 2nd frame under
768px, and holds the final frame under `prefers-reduced-motion`.

## Notes

- Voice ships on the native Web Speech API; the seam to swap in a premium TTS
  (e.g. ElevenLabs) is in `src/hooks/useSpeech.js` and `server/claude.js`.
- This is a research-stage screening platform, not a diagnostic device.
