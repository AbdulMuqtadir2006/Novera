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

Deploys to **Cloudflare Pages** at `www.novera.fun`. The backend deploys separately to
**Railway** at `api.novera.fun` — see [`../backend/README.md`](../backend/README.md).

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
3. Add env var `VITE_API_URL=https://api.novera.fun` under the project's **Settings → Environment variables**.
4. **Custom domains** tab → add `www.novera.fun` (and `novera.fun` with a redirect, if desired). If the domain's nameservers are already on Cloudflare, this activates instantly; otherwise Cloudflare gives you the CNAME/records to add at your registrar.
5. Cloudflare's current Git integration deploys this as a **Worker with static assets** (via `npx wrangler deploy`), not classic Pages — `wrangler.jsonc` in this folder configures that: `assets.directory: "./dist"` plus `not_found_handling: "single-page-application"` so client-side routing (React Router) works on refresh/deep links. Without `wrangler.jsonc`, Wrangler tries to auto-configure via its Vite plugin, which requires Vite 6+ — this repo pins Vite 5, so the config file avoids that path entirely. **Don't add a `public/_redirects` file** — it conflicts with `not_found_handling` and Cloudflare rejects the deploy with an "infinite loop" error on the `/index.html` rule.

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

The 240 hero frames are in `public/frames/` as `frame_0001.jpg … frame_0240.jpg` (1280×720,
desktop) and `public/frames-mobile/` at the same names (720×1280, portrait — served instead on
screens ≤767px so the hero isn't cover-cropped from a landscape composition). Scrub logic:
`src/hooks/useScrollFrameSequence.js`.

## Android app (Capacitor)

This same React app is wrapped as a native Android app via [Capacitor](https://capacitorjs.com) —
`capacitor.config.json` + the generated `android/` project (source only; `android/app/build/` and
`android/.gradle/` are gitignored, regenerated on build).

- **Building an APK**: handled by `.github/workflows/android-build.yml` — on every push touching
  `frontend/**`, it builds the web app (`VITE_API_URL` pinned to the production API), runs
  `npx cap sync android`, builds a debug APK with Gradle, and publishes it to the repo's
  `latest-android-build` GitHub Release. No local Android Studio/SDK required.
- **Local dev** (if you do have Android Studio installed): `npm run build && npx cap sync android`,
  then `npx cap open android` to launch Studio, or `npx cap run android` with a device/emulator
  connected.
- **App icon / splash source**: `assets/icon.png`, `assets/icon-foreground.png`, `assets/splash.png`
  (the logo mark on the `ink` background color). Regenerate all densities after changing these with
  `npx capacitor-assets generate --android --iconBackgroundColor '#080919' --iconBackgroundColorDark '#080919' --splashBackgroundColor '#080919' --splashBackgroundColorDark '#080919'`.
- **CORS note**: the Android WebView calls the API from the `https://localhost` origin (Capacitor's
  default virtual host) — already whitelisted in the backend's `CORS_ORIGINS`.
- This is a debug build for direct install, not signed for the Play Store. Release signing
  (keystore + Play Store listing) is a separate step if that's ever needed.

## Notes

This is a research-stage screening platform, not a diagnostic device.
