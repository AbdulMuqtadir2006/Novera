# Novera — Frontend

Marketing site + product app for **Novera**, an agentic AI-driven saliva biosensor platform for
non-invasive health screening. React + Vite, talking to the [`backend/`](../backend) FastAPI
service over HTTP.

## Architecture

```
Browser (React + Vite)
   │  VITE_API_URL (or /api dev proxy)
   ▼
FastAPI backend (Railway, Postgres)
   ├── auth, dashboard readings, patient context, chat
   ├── LangGraph agents → OpenRouter  [report · voice · self-care · chat · organ screening]
   └── Meta WhatsApp Cloud API (appointment booking + Q&A)
```

Deploys to **Vercel** at `www.echo-nova.online`. The backend deploys separately to **Railway** at
`api.echo-nova.online` — see [`../backend/README.md`](../backend/README.md).

- **Stack:** React 18, Vite, Tailwind, Framer Motion, GSAP (frame-scrub hero), Recharts,
  lucide-react, jsPDF + html2canvas (bilingual PDF), Web Speech API.
- Every AI call has a deterministic **bilingual fallback** server-side, so the app stays fully
  functional even if the AI service or OpenRouter is unavailable.

## Run it

```bash
npm install
cp .env.example .env          # set VITE_API_URL, or leave unset to use the dev proxy
npm run dev                   # http://localhost:5173
```

Requires the backend running (`../backend`, `uvicorn app.main:app --reload` on :8000) for real
data — see that folder's README for setup.

`npm run build` produces the production bundle in `dist/` (what Vercel deploys).

## Features

| Route | What it does |
|---|---|
| `/` | Frame-scrub hero, agents pipeline, health areas, how-it-works, CTA. |
| `/dashboard` | Live readings, metric cards + sparklines, screening gauge, trend charts. **Simulate new sample** adds a row — voice/report/self-care all update from it. |
| `/reports` | AI-written screening report (EN/AR), regenerated per sample. Bilingual PDF via html2canvas. |
| `/voice` | AI voice script read aloud via Web Speech API. |
| `/self-care` | AI diet plan + per-area guidance, plus a coach chatbot that stores doctor context. |
| `/more` | **Appointments** — agentic WhatsApp booking simulator, deep organ-screening analysis, clinic info, bookings list. |

## Bilingual (EN / AR)

Language toggle in the navbar, persisted in `localStorage`. Arabic switches the document to RTL
and the Cairo font. UI strings live in `src/i18n/translations.js`; AI content is generated in the
selected language by the backend.

## Frame sequence

The 240 hero frames are in `public/frames/` as `frame_0001.jpg … frame_0240.jpg` (1280×720).
Scrub logic: `src/hooks/useScrollFrameSequence.js`.

## Notes

This is a research-stage screening platform, not a diagnostic device.
