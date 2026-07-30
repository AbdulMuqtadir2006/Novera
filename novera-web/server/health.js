// Shared biomarker reference ranges + status logic (backend source of truth).
export const REFERENCE = {
  ph: { unit: "", range: [6.2, 7.6], dp: 2, label: "pH" },
  creatinine: { unit: "mg/dL", range: [0.6, 1.3], dp: 2, label: "Creatinine" },
  urea: { unit: "mg/dL", range: [7, 20], dp: 1, label: "Urea" },
  temperature: { unit: "°C", range: [36.1, 37.2], dp: 1, label: "Temperature" },
};

const RANK = { good: 0, watch: 1, attention: 2 };

export function statusFor(value, [low, high], softPad = 0.12) {
  const span = high - low;
  const pad = span * softPad;
  if (value < low - pad || value > high + pad) return "attention";
  if (value < low || value > high) return "watch";
  return "good";
}

function worst(a, b) {
  return RANK[a] >= RANK[b] ? a : b;
}

// Turn a raw DB row into the reading shape the frontend expects.
export function rowToReading(row) {
  const metrics = {};
  for (const key of Object.keys(REFERENCE)) {
    const ref = REFERENCE[key];
    const value = row[key];
    metrics[key] = {
      value,
      unit: ref.unit,
      range: ref.range,
      status: statusFor(value, ref.range),
    };
  }
  const healthAreas = {
    kidney: worst(metrics.creatinine.status, metrics.urea.status),
    hydration: metrics.urea.status === "good" ? "good" : "watch",
    oral: metrics.ph.status,
    digestive: worst(metrics.ph.status, metrics.temperature.status),
  };
  return { id: row.id, timestamp: row.timestamp, metrics, healthAreas };
}
