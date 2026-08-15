// API layer — talks to the Novera FastAPI backend (Postgres + OpenRouter).
// VITE_API_URL points at the deployed backend (e.g. https://api.echo-nova.online);
// unset in dev, requests fall back to Vite's proxy (see vite.config.js).

const API_BASE = import.meta.env.VITE_API_URL || "";
const TOKEN_KEY = "novera-token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) =>
  t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY);

async function req(path, options = {}) {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${res.status}`);
  }
  return res.json();
}

// ---- auth ----
export const signup = (payload) =>
  req("/auth/signup", { method: "POST", body: JSON.stringify(payload) });
export const login = (email, password) =>
  req("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const fetchMe = () => req("/auth/me");
export const logoutApi = () => req("/auth/logout", { method: "POST" });

export const getLatestReading = () => req("/readings/latest");
export const getReadingHistory = (days = 30) => req(`/readings?days=${days}`);
export const addReading = (values) =>
  req("/readings", { method: "POST", body: JSON.stringify(values || {}) });

export const getDeviceStatus = () => req("/device/status");
export const requestSample = () => req("/device/request-sample", { method: "POST" });

export const getHealth = () => req("/health");

export const getPatientContext = () => req("/patient-context");
export const savePatientContext = (ctx) =>
  req("/patient-context", { method: "POST", body: JSON.stringify(ctx) });

export const getVoiceScript = (lang) =>
  req("/voice-script", { method: "POST", body: JSON.stringify({ lang }) });
export const getReport = (lang) =>
  req("/report", { method: "POST", body: JSON.stringify({ lang }) });
// `force: false` (default) returns the persisted plan instantly if one
// exists — no LLM call. `force: true` always regenerates from scratch
// (used by the "Regenerate" button).
export const getSelfCare = (lang, { force = false } = {}) =>
  req("/self-care", { method: "POST", body: JSON.stringify({ lang, force }) });

export const getChat = () => req("/chat");
export const sendChat = (message, lang) =>
  req("/chat", { method: "POST", body: JSON.stringify({ message, lang }) });
export const resetChat = () => req("/chat", { method: "DELETE" });

// Agentic extras (via the Python LangGraph service)
export const predictOrgan = () => req("/predict-organ", { method: "POST", body: "{}" });

// Same screening pipeline as predictOrgan(), streamed as real backend events
// (validate/score-per-organ/decide/persist, each only after it actually
// happens) — for a workflow visualizer driven by genuine progress, not a
// timer. A plain POST (not native EventSource, which can't send the
// Authorization header) — the body is read and parsed as SSE by hand.
// onEvent fires once per step; the returned promise resolves with the same
// final result shape predictOrgan() returns, or rejects on pipeline failure.
export async function streamPredictOrgan(onEvent) {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/predict-organ/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: "{}",
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalStatus = null;
  let finalResult = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const line = chunk.trim();
      if (!line.startsWith("data:")) continue;
      let event;
      try {
        event = JSON.parse(line.slice(5).trim());
      } catch {
        continue;
      }
      onEvent?.(event);
      if (event.step === "done") {
        finalStatus = event.status;
        finalResult = event.result;
      }
    }
  }

  if (finalStatus !== "passed") {
    const err = new Error(finalResult?.message || finalResult?.reason || "Screening pipeline failed");
    err.result = finalResult;
    throw err;
  }
  // Normalize to the same shape predictOrgan() returns, so callers don't
  // need to know about the backend's internal ai_* field names.
  return {
    prediction: finalResult.ai_prediction,
    confidence: finalResult.ai_confidence,
    reason: finalResult.ai_reason,
    source: "ai",
    case_id: finalResult.case_id,
    specialist_results: finalResult.specialist_results,
  };
}
export const getClinic = () => req("/clinic");
export const sendAppointmentOffer = (opts = {}) =>
  req("/appointment/offer", { method: "POST", body: JSON.stringify(opts) });
export const replyAppointment = (message, lang) =>
  req("/appointment/reply", { method: "POST", body: JSON.stringify({ message, lang }) });
export const getBookings = () => req("/appointment/bookings");
