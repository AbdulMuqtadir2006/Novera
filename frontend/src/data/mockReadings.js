// Mock sensor readings standing in for the SQL-backed API (see brief §10).
// Generated deterministically so the trend charts have ~30 days of plausible,
// slightly noisy data without a build-time random reshuffle on every reload.

const REFERENCE = {
  ph: { unit: "", range: [6.2, 7.6] },
  creatinine: { unit: "mg/dL", range: [0.6, 1.3] },
  urea: { unit: "mg/dL", range: [7, 20] },
  temperature: { unit: "°C", range: [36.1, 37.2] },
};

// Small seeded PRNG (mulberry32) — deterministic across reloads.
function mulberry32(seed) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function statusFor(value, [low, high], softPad = 0.12) {
  const span = high - low;
  const pad = span * softPad;
  if (value < low - pad || value > high + pad) return "attention";
  if (value < low || value > high) return "watch";
  return "good";
}

function round(v, dp) {
  const f = 10 ** dp;
  return Math.round(v * f) / f;
}

function buildReadings(days = 30) {
  const rand = mulberry32(20260726);
  const readings = [];
  // Anchor at the brief's example timestamp so "latest" reads 2026-07-25.
  const end = new Date("2026-07-25T09:14:00Z").getTime();
  const dayMs = 24 * 60 * 60 * 1000;

  for (let i = days - 1; i >= 0; i--) {
    const t = end - i * dayMs;
    // Gentle sinusoidal drift + noise per metric.
    const phase = (days - i) / days;

    const ph = round(6.7 + Math.sin(phase * 6) * 0.35 + (rand() - 0.5) * 0.25, 2);
    const creatinine = round(
      0.95 + Math.sin(phase * 4 + 1) * 0.18 + (rand() - 0.5) * 0.12,
      2
    );
    // Urea trends slightly high toward the present -> gives a "watch" latest.
    const urea = round(
      18 + phase * 8 + Math.sin(phase * 5) * 3 + (rand() - 0.5) * 3,
      1
    );
    const temperature = round(
      36.8 + Math.sin(phase * 3) * 0.25 + (rand() - 0.5) * 0.2,
      1
    );

    const metrics = {
      ph: { value: ph, unit: REFERENCE.ph.unit, range: REFERENCE.ph.range, status: statusFor(ph, REFERENCE.ph.range) },
      creatinine: {
        value: creatinine,
        unit: REFERENCE.creatinine.unit,
        range: REFERENCE.creatinine.range,
        status: statusFor(creatinine, REFERENCE.creatinine.range),
      },
      urea: {
        value: urea,
        unit: REFERENCE.urea.unit,
        range: REFERENCE.urea.range,
        status: statusFor(urea, REFERENCE.urea.range),
      },
      temperature: {
        value: temperature,
        unit: REFERENCE.temperature.unit,
        range: REFERENCE.temperature.range,
        status: statusFor(temperature, REFERENCE.temperature.range),
      },
    };

    // Map biomarkers -> health-area statuses.
    const healthAreas = {
      kidney: worst(metrics.creatinine.status, metrics.urea.status),
      hydration: metrics.urea.status === "good" ? "good" : "watch",
      oral: metrics.ph.status,
      digestive: worst(metrics.ph.status, metrics.temperature.status),
    };

    readings.push({
      timestamp: new Date(t).toISOString(),
      metrics,
      healthAreas,
    });
  }
  return readings;
}

const RANK = { good: 0, watch: 1, attention: 2 };
function worst(a, b) {
  return RANK[a] >= RANK[b] ? a : b;
}

export const mockReadings = buildReadings(30);
export { REFERENCE };
