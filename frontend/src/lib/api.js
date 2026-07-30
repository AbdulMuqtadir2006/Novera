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

export const getHealth = () => req("/health");

export const getPatientContext = () => req("/patient-context");
export const savePatientContext = (ctx) =>
  req("/patient-context", { method: "POST", body: JSON.stringify(ctx) });

export const getVoiceScript = (lang) =>
  req("/voice-script", { method: "POST", body: JSON.stringify({ lang }) });
export const getReport = (lang) =>
  req("/report", { method: "POST", body: JSON.stringify({ lang }) });
export const getSelfCare = (lang) =>
  req("/self-care", { method: "POST", body: JSON.stringify({ lang }) });

export const getChat = () => req("/chat");
export const sendChat = (message, lang) =>
  req("/chat", { method: "POST", body: JSON.stringify({ message, lang }) });
export const resetChat = () => req("/chat", { method: "DELETE" });

// Agentic extras (via the Python LangGraph service)
export const predictOrgan = () => req("/predict-organ", { method: "POST", body: "{}" });
export const getClinic = () => req("/clinic");
export const sendAppointmentOffer = (opts = {}) =>
  req("/appointment/offer", { method: "POST", body: JSON.stringify(opts) });
export const replyAppointment = (message, lang) =>
  req("/appointment/reply", { method: "POST", body: JSON.stringify({ message, lang }) });
export const getBookings = () => req("/appointment/bookings");
