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

Deploys to **Cloudflare Pages** at `www.echo-nova.online`. The backend deploys separately to
**Railway** at `api.echo-nova.online` — see [`../backend/README.md`](../backend/README.md).

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

`npm run build` produces the production bundle in `dist/` (what Cloudflare Pages deploys).

## Deploying to Cloudflare Pages

1. Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**, pick this repo.
2. Build settings: root directory `frontend/`, build command `npm run build`, build output directory `dist`.
3. Add env var `VITE_API_URL=https://api.echo-nova.online` under the project's **Settings → Environment variables**.
4. **Custom domains** tab → add `www.echo-nova.online` (and `echo-nova.online` with a redirect, if desired). If the domain's nameservers are already on Cloudflare, this activates instantly; otherwise Cloudflare gives you the CNAME/records to add at your registrar.
5. Cloudflare's current Git integration deploys this as a **Worker with static assets** (via `npx wrangler deploy`), not classic Pages — `wrangler.jsonc` in this folder configures that: `assets.directory: "./dist"` plus `not_found_handling: "single-page-application"` so client-side routing (React Router) works on refresh/deep links. (`public/_redirects` is also in the repo as a harmless fallback, but the Worker's SPA fallback is what actually handles this.) Without `wrangler.jsonc`, Wrangler tries to auto-configure via its Vite plugin, which requires Vite 6+ — this repo pins Vite 5, so the config file avoids that path entirely.

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
