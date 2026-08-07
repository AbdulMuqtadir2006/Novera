# Novera — Backend

FastAPI service on Postgres: auth, dashboard readings, patient context, the content agents
(voice/report/self-care/chat via OpenRouter), the deterministic organ-screening pipeline, and the
Meta WhatsApp Cloud API appointment/Q&A agent. Replaces what used to be a Node/Express backend +
a separate Python AI service.

## Architecture

```
Browser (React frontend, Cloudflare Pages)
   │  /api/*
   ▼
FastAPI (Railway)                          Postgres (Railway)
   ├── auth, readings, patient context ───► readings, patient_context, chat_messages, users, sessions
   ├── content agents (OpenRouter)
   ├── screening pipeline: reference-range score + similarity score
   │     (SQL-limited confirmed_cases) + exactly one OpenRouter call ──► screening_cases, confirmed_cases, decision_audit
   └── WhatsApp: GET/POST /webhook ───────► appointments
         ├── booking → core/booking.py (Postgres, double-booking safe, no LLM)
         └── Q&A → facts from Postgres, phrased by one OpenRouter call
```

Every AI call has a deterministic bilingual fallback (`core/fallbacks.py`) — the app stays
functional even without an OpenRouter key or if OpenRouter is down. The one exception, by design:
the screening pipeline's final decision (req 8) — if OpenRouter fails, the case is released back
to `NEW` with **no saved prediction and no invented reason**, never silently faked.

## Local setup

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt                # macOS/Linux

cp .env.example .env   # fill in DATABASE_URL (a local Postgres) + OPENROUTER_API_KEY

python scripts/init_db.py                 # creates tables, seeds reference ranges + demo readings
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
# health: http://127.0.0.1:8000/api/health
```

### Migrating legacy screening data (req 4)

If you have the old `Novera ai part/novera.db` (SQLite, cases N001–N150):

```bash
python scripts/migrate_sqlite_to_pg.py --sqlite-path "/path/to/novera.db"
```

Idempotent — re-running never creates duplicates (`ON CONFLICT (case_id) DO NOTHING`).

### Ops CLI

`scripts/screening_cli.py` — add a case, process the latest NEW one, confirm a case's real organ
(builds the similarity-scoring memory), or inspect cases. No UI does case confirmation, so this is
the way to do it:

```bash
python scripts/screening_cli.py confirm --case-id N151 --organ KIDNEY --confirmed-by "Dr. Amal"
python scripts/screening_cli.py list --limit 10
```

## Deploying to Railway

1. New Railway project → **Deploy from GitHub repo**, root directory `backend/`.
2. Add a **Postgres** plugin to the project — Railway injects `DATABASE_URL` automatically.
3. Set the other env vars from `.env.example` (`OPENROUTER_API_KEY` at minimum; `META_*` when you
   go live on WhatsApp) in the service's Variables tab. **Never commit real values** — `.env` is
   gitignored and `.env.example` only holds placeholders (req 17).
4. Railway reads `railway.json` — build via Nixpacks, start command
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (entry point `app.main:app`).
5. After the first deploy, run once (Railway's shell, or a one-off run):
   ```bash
   python scripts/init_db.py
   ```
6. Point a custom domain at the service: `api.echo-nova.online`.

## Deploying the frontend (Cloudflare Pages)

See [`../frontend/README.md`](../frontend/README.md). Set `VITE_API_URL=https://api.echo-nova.online`
in the Cloudflare Pages project's environment variables, and point `www.echo-nova.online` at it.

## Going live on WhatsApp (Meta Cloud API)

1. In **developers.facebook.com**, create a Business app → add the **WhatsApp** product. Copy the
   **access token** and **Phone Number ID** from *API Setup*.
2. Set `META_WHATSAPP_TOKEN`, `META_PHONE_NUMBER_ID`, `META_VERIFY_TOKEN`, and `WHATSAPP_TO` in the
   Railway service's env vars.
3. In **WhatsApp → Configuration → Webhook**: Callback URL `https://api.echo-nova.online/webhook`,
   Verify token = your `META_VERIFY_TOKEN`. Click *Verify and Save*, then subscribe to `messages`.
4. Inbound messages are routed by `core/whatsapp_agent.py`: booking always goes through
   `core/booking.py` (Postgres, can't double-book, can't have an invented time — req 13); questions
   about a patient's report/biomarkers/doctor notes/appointments are answered only from that
   patient's real data in Postgres (matched by their registered phone number), phrased by one
   OpenRouter call constrained to those facts (req 12).

> Meta only allows free-form text within **24h** of the user's last message. Business-initiated
> messages outside that window require an approved template.

## Environment variables

See `.env.example` for the full list. Nothing is ever hardcoded (req 17) — `app/config.py` reads
everything from the environment.

## Notes

This is a research-stage screening platform, not a diagnostic device. No trained ML model,
XGBoost, scikit-learn, or `.pkl` file is used anywhere — every prediction is reference-range score
+ similarity score + exactly one OpenRouter decision call, and the final label is always exactly
one of `KIDNEY`, `STOMACH`, `ORAL`.
