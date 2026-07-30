import "dotenv/config";
import express from "express";
import cors from "cors";
import { db, initSchema, countReadings } from "./db.js";
import { rowToReading, REFERENCE } from "./health.js";
import {
  createUser,
  authenticate,
  createSession,
  deleteSession,
  attachUser,
} from "./auth.js";
import {
  generateVoiceScript,
  generateReport,
  generateSelfCare,
  chat,
  predictOrgan,
  appointmentOffer,
  appointmentReply,
  listBookings,
  getClinic,
  serviceHealth,
  runPipeline,
  orchestratorWhatsApp,
} from "./claude.js";

initSchema();

const app = express();
app.use(cors());
app.use(express.json({ limit: "1mb" }));
app.use(attachUser); // sets req.user / req.token from Bearer token (if any)

const PORT = process.env.PORT || 3001;

// ---- auth ----
app.post("/api/auth/signup", (req, res) => {
  try {
    const user = createUser(req.body || {});
    const token = createSession(user.id);
    res.status(201).json({ token, user });
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

app.post("/api/auth/login", (req, res) => {
  const { email, password } = req.body || {};
  const user = authenticate(email, password);
  if (!user) return res.status(401).json({ error: "Invalid email or password" });
  const token = createSession(user.id);
  res.json({ token, user });
});

app.get("/api/auth/me", (req, res) => {
  if (!req.user) return res.status(401).json({ error: "Not authenticated" });
  res.json({ user: req.user });
});

app.post("/api/auth/logout", (req, res) => {
  deleteSession(req.token);
  res.json({ ok: true });
});

// ---- helpers ----
function getLatestRow() {
  return db.prepare("SELECT * FROM readings ORDER BY datetime(timestamp) DESC, id DESC LIMIT 1").get();
}
function getContext() {
  return db.prepare("SELECT diagnosis, medications, notes, updated_at FROM patient_context WHERE id = 1").get() || { diagnosis: "", medications: "", notes: "" };
}
function getChatHistory() {
  return db.prepare("SELECT role, content, lang, created_at FROM chat_messages ORDER BY id ASC").all();
}
const round = (v, dp) => Math.round(v * 10 ** dp) / 10 ** dp;

// ---- meta ----
app.get("/api/health", async (_req, res) => {
  const ai = await serviceHealth();
  res.json({ ok: true, ai, readings: countReadings() });
});

// ---- readings ----
app.get("/api/readings/latest", (_req, res) => {
  const row = getLatestRow();
  if (!row) return res.status(404).json({ error: "no readings" });
  res.json(rowToReading(row));
});

app.get("/api/readings", (req, res) => {
  const days = Math.max(1, Math.min(365, parseInt(req.query.days) || 30));
  const rows = db
    .prepare("SELECT * FROM readings ORDER BY datetime(timestamp) DESC, id DESC LIMIT ?")
    .all(days)
    .reverse();
  res.json(rows.map(rowToReading));
});

// Add a new reading (simulates a fresh sample landing in the DB). Optional body
// values; otherwise generate a plausible reading near the last one.
app.post("/api/readings", (req, res) => {
  const last = getLatestRow();
  const jitter = (base, amp, dp) => round(base + (Math.random() - 0.5) * amp, dp);
  const b = req.body || {};
  const reading = {
    ph: b.ph ?? jitter(last ? last.ph : 6.8, 0.6, 2),
    creatinine: b.creatinine ?? jitter(last ? last.creatinine : 1.0, 0.4, 2),
    urea: b.urea ?? jitter(last ? last.urea : 22, 8, 1),
    temperature: b.temperature ?? jitter(last ? last.temperature : 36.9, 0.6, 1),
  };
  const timestamp = new Date().toISOString();
  const info = db
    .prepare("INSERT INTO readings (timestamp, ph, creatinine, urea, temperature) VALUES (?, ?, ?, ?, ?)")
    .run(timestamp, reading.ph, reading.creatinine, reading.urea, reading.temperature);
  const row = db.prepare("SELECT * FROM readings WHERE id = ?").get(info.lastInsertRowid);
  res.status(201).json(rowToReading(row));
});

// ---- patient context ----
app.get("/api/patient-context", (_req, res) => {
  res.json(getContext());
});

app.post("/api/patient-context", (req, res) => {
  const { diagnosis = "", medications = "", notes = "" } = req.body || {};
  db.prepare(
    "UPDATE patient_context SET diagnosis = ?, medications = ?, notes = ?, updated_at = ? WHERE id = 1"
  ).run(diagnosis, medications, notes, new Date().toISOString());
  res.json(getContext());
});

// ---- AI: voice ----
app.post("/api/voice-script", async (req, res) => {
  const row = getLatestRow();
  if (!row) return res.status(404).json({ error: "no readings" });
  const lang = req.body?.lang === "ar" ? "ar" : "en";
  const out = await generateVoiceScript(rowToReading(row), lang);
  res.json(out);
});

// ---- AI: report ----
app.post("/api/report", async (req, res) => {
  const row = getLatestRow();
  if (!row) return res.status(404).json({ error: "no readings" });
  const lang = req.body?.lang === "ar" ? "ar" : "en";
  const out = await generateReport(rowToReading(row), getContext(), lang);
  res.json(out);
});

// ---- AI: self-care ----
app.post("/api/self-care", async (req, res) => {
  const row = getLatestRow();
  if (!row) return res.status(404).json({ error: "no readings" });
  const lang = req.body?.lang === "ar" ? "ar" : "en";
  const out = await generateSelfCare(rowToReading(row), getContext(), getChatHistory(), lang);
  res.json(out);
});

// ---- AI: chat ----
app.get("/api/chat", (_req, res) => {
  res.json({ messages: getChatHistory(), context: getContext() });
});

app.post("/api/chat", async (req, res) => {
  const message = (req.body?.message || "").trim();
  const lang = req.body?.lang === "ar" ? "ar" : "en";
  if (!message) return res.status(400).json({ error: "empty message" });

  const now = new Date().toISOString();
  db.prepare("INSERT INTO chat_messages (role, content, lang, created_at) VALUES ('user', ?, ?, ?)").run(message, lang, now);

  const row = getLatestRow();
  const reading = row ? rowToReading(row) : null;
  const ctx = getContext();
  const history = getChatHistory();

  const out = await chat(history, reading, ctx, lang);

  db.prepare("INSERT INTO chat_messages (role, content, lang, created_at) VALUES ('assistant', ?, ?, ?)").run(out.reply, lang, new Date().toISOString());

  if (out.contextChanged) {
    db.prepare(
      "UPDATE patient_context SET diagnosis = ?, medications = ?, notes = ?, updated_at = ? WHERE id = 1"
    ).run(out.diagnosis || "", out.medications || "", out.notes || "", new Date().toISOString());
  }

  res.json({ reply: out.reply, context: getContext(), contextChanged: !!out.contextChanged, source: out.source });
});

// Reset chat (optional utility)
app.delete("/api/chat", (_req, res) => {
  db.exec("DELETE FROM chat_messages");
  res.json({ ok: true });
});

// ---- agentic: organ prediction (deep AI analysis) ----
app.post("/api/predict-organ", async (_req, res) => {
  const row = getLatestRow();
  if (!row) return res.status(404).json({ error: "no readings" });
  try {
    const out = await predictOrgan(rowToReading(row));
    res.json(out);
  } catch (e) {
    res.status(502).json({ error: "AI service unavailable", detail: e.message });
  }
});

// ---- appointment / WhatsApp ----
app.get("/api/clinic", async (_req, res) => {
  try {
    res.json(await getClinic());
  } catch (e) {
    res.status(502).json({ error: e.message });
  }
});

// Send the WhatsApp "book an appointment?" offer. Body: { to?, simulate? }
app.post("/api/appointment/offer", async (req, res) => {
  const row = getLatestRow();
  const caseId = row ? `N${String(row.id).padStart(3, "0")}` : null;
  // Prefer the logged-in user's phone; fall back to a body-provided number.
  const phone = req.user?.phone || req.body?.to || undefined;
  const to = phone ? (phone.startsWith("whatsapp:") ? phone : `whatsapp:${phone}`) : undefined;
  try {
    const out = await appointmentOffer({
      to,
      case_id: caseId,
      simulate: req.body?.simulate !== false, // default simulate=true for safety
    });
    res.json({ ...out, sentTo: to || null });
  } catch (e) {
    res.status(502).json({ error: "AI service unavailable", detail: e.message });
  }
});

// Local simulator for the inbound WhatsApp reply (no Twilio needed). Body: { message, lang }
app.post("/api/appointment/reply", async (req, res) => {
  const message = (req.body?.message || "").trim();
  const lang = req.body?.lang === "ar" ? "ar" : "en";
  if (!message) return res.status(400).json({ error: "empty message" });
  try {
    res.json(await appointmentReply(message, lang));
  } catch (e) {
    res.status(502).json({ error: "AI service unavailable", detail: e.message });
  }
});

app.get("/api/appointment/bookings", async (_req, res) => {
  try {
    res.json(await listBookings());
  } catch (e) {
    res.status(502).json({ error: e.message });
  }
});

// ---- agentic orchestrator (LangGraph) ----
// Runs the full pipeline on the latest reading (from the web DB).
app.post("/api/orchestrator/run", async (_req, res) => {
  const row = getLatestRow();
  if (!row) return res.status(404).json({ error: "no readings" });
  const reading = {
    ph: row.ph,
    creatinine: row.creatinine,
    urea: row.urea,
    temperature: row.temperature,
  };
  try {
    res.json(await runPipeline(reading));
  } catch (e) {
    res.status(502).json({ error: "AI service unavailable", detail: e.message });
  }
});

app.post("/api/orchestrator/whatsapp", async (req, res) => {
  const message = (req.body?.message || "").trim();
  if (!message) return res.status(400).json({ error: "empty message" });
  try {
    res.json(await orchestratorWhatsApp(message));
  } catch (e) {
    res.status(502).json({ error: "AI service unavailable", detail: e.message });
  }
});

app.listen(PORT, () => {
  console.log(`Novera API on http://localhost:${PORT} (AI service: ${process.env.AI_SERVICE_URL || "http://127.0.0.1:8000"})`);
});
