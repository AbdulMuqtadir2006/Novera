# NOVERA — Agentic AI Service

The AI "brain" behind the Novera web app: a **FastAPI** service driven by
**LangGraph** agents, using **OpenRouter** free models (unified across the whole
product) and the **Meta WhatsApp Cloud API** for the appointment flow. The web
app's Node backend calls this service over HTTP.

```
Frontend (React)  →  Node backend (:3001)  →  THIS service (:8000)  →  OpenRouter
                                                          └────────→  Meta WhatsApp Cloud API
```

## Agents

| Agent | Endpoint | What it does |
|---|---|---|
| Voice | `POST /ai/voice` | Spoken screening summary (EN/AR) |
| Report | `POST /ai/report` | Plain-language screening report (EN/AR), doctor-context aware |
| Self-care | `POST /ai/self-care` | Personalised diet plan + per-area tips, shaped by doctor context |
| Chat | `POST /ai/chat` | Doctor-context coach; maintains diagnosis/medications/notes |
| Organ prediction | `POST /ai/predict-organ` | **LangGraph** pipeline: 3 deterministic specialist scorers (kidney/stomach/oral) → one LLM decision |
| Appointment | `POST /appointment/reply` | **LangGraph** agent: understand reply → book slot → compose confirmation |
| WhatsApp offer | `POST /appointment/offer` | Sends the "book an appointment?" WhatsApp message (or simulates) |
| WhatsApp webhook | `GET/POST /whatsapp/webhook` | Meta webhook: GET verifies, POST handles inbound JSON + replies via Graph API |
| Bookings / clinic | `GET /appointment/bookings`, `GET /clinic` | Booking log + Badr Al Samaa location |

Every AI call has a **deterministic bilingual fallback**, so the service never
fails even if the LLM is slow, rate-limited, or returns bad JSON.

## The appointment booking rule (Badr Al Samaa, Al Khuwair)

Implemented in `novera_ai/clinic.py`:

- Clinic open, doctor **not** on break → book **now + 30 minutes**.
- Doctor **on break** (13:00–16:00) → book **next day 08:00**.
- `now + 30` would land in the break or after closing (22:00) → **next day 08:00**.
- Before opening (08:00) → **today 08:00**.

The confirmation includes the time, address, **Google Maps link**, and phone.

## Agentic orchestrator (LangGraph)

`novera_ai/orchestrator/` is the full screening pipeline from the architecture
brief — a LangGraph graph of 12 agents over a shared `NoveraState`:

`capture → qa → orchestrator(Boss) →[analysis|loop back] analysis → insight →
guidance → voice → report →[hardcoded threshold gate]→ whatsapp_notifier`

plus a WhatsApp-reply graph (`multi_language → book/report/explain/decline`).

- **3 agentic decisions** (Boss LLM): QA proceed-vs-loop, WhatsApp intent, and
  language detection. Everything else is a fixed edge.
- **Hardcoded safety gate**: `check_threshold()` in `state.py` (pure Python,
  never an LLM) sets `threshold_crossed`; the graph escalates to WhatsApp on it.
- **QA loop** caps at 2 (never loops forever).
- SQLite (`orchestrator/orchestrator.db`, seeded with a demo user + doctor slots),
  ReportLab PDF (`orchestrator/reports/`), and the WhatsApp + clinic tools.
- Runs today on the OpenRouter/deterministic fallbacks; swap to `claude-sonnet-4-6`
  + real WhatsApp/TTS at the API-key step.

**Endpoints:** `POST /orchestrator/run`, `POST /orchestrator/whatsapp`,
`GET /orchestrator/user/{id}`, `GET /orchestrator/slots`,
`GET /orchestrator/report/{reading_id}`. The web app triggers it from the
Appointments page ("Run full AI pipeline") and shows the live agent trace.

**LangGraph Studio:** `pip install langgraph-cli` then `langgraph dev`
(config in `langgraph.json`, graphs `novera` + `novera_whatsapp`).

## Setup

```bash
cd "Novera ai part"
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt               # macOS/Linux
```

> Note: the old `.venv-1/` in this folder is broken (points at a removed Python
> 3.13) — ignore it; use the fresh `.venv/`.

`.env` keys used:

```
OPENROUTER_API_KEY=sk-or-...      # powers every agent (free models via 'auto')
OPENROUTER_MODEL=auto             # 'auto' -> openrouter/free auto-router
META_WHATSAPP_TOKEN=EAAG...       # WhatsApp (optional until you go live)
META_PHONE_NUMBER_ID=123456789    # numeric Phone Number ID from the Meta dashboard
META_VERIFY_TOKEN=novera_verify_123   # you invent this; must match the webhook config
META_APP_SECRET=                  # optional: verifies X-Hub-Signature-256 on inbound
META_API_VERSION=v22.0
WHATSAPP_TO=+9689...              # your number in E.164 (add to go live)
```

## Run

```bash
.venv/Scripts/python -m uvicorn api:app --host 127.0.0.1 --port 8000
# health: http://127.0.0.1:8000/health
```

Then run the web app (`../novera-web`): the Node backend reads `AI_SERVICE_URL`
(default `http://127.0.0.1:8000`) and delegates all AI to this service.

**Run order:** this service (:8000) → Node backend (:3001) → Vite (`npm run dev`).

## The original CLI (`novera.py`)

The organ-screening core is still runnable as a standalone CLI and remains the
source of the deterministic specialist scoring the service reuses:

```bash
.venv/Scripts/python novera.py init-db
.venv/Scripts/python novera.py add-reading --ph 6.8 --urea 24 --creatinine 20 --temperature 36.8
.venv/Scripts/python novera.py process     # one OpenRouter decision
.venv/Scripts/python novera.py list
```

## Going live on WhatsApp (Meta Cloud API)

The appointment flow is fully testable **without Meta** via the local simulator
(`/appointment/reply`, and the Appointments page in the web app). To send/receive
real WhatsApp messages:

1. In **developers.facebook.com**, create a Business app → add the **WhatsApp**
   product. Copy the **access token** and **Phone Number ID** from *API Setup*.
2. Set `META_WHATSAPP_TOKEN`, `META_PHONE_NUMBER_ID`, `META_VERIFY_TOKEN`, and
   `WHATSAPP_TO=+<your number>` in `.env`.
3. Expose this service publicly over HTTPS, e.g. `ngrok http 8000` (or
   `tools/cloudflared.exe tunnel --url http://localhost:8000`).
4. In **WhatsApp → Configuration → Webhook**, set the **Callback URL** to
   `https://<your-tunnel>/whatsapp/webhook` and the **Verify token** to the same
   `META_VERIFY_TOKEN`. Click *Verify and Save*, then subscribe to the
   **`messages`** field.
5. Message the number first (opens the 24h window), then trigger an offer
   (`POST /appointment/offer` with `"simulate": false`), reply **OK** on WhatsApp,
   and the agent books + replies with the confirmation.

> Meta only allows free-form text within **24h** of the user's last message.
> Business-initiated messages outside that window require an approved template.

## What changed from the original

- `agent.py` (weather demo) and `whatsapp_test.py` (echo stub) are superseded by
  the real agents in `novera_ai/` and `api.py`.
- `novera.py` (the good organ-prediction pipeline) is **kept and reused** — the
  service imports its `ScoringEngine` for deterministic specialist scoring.
