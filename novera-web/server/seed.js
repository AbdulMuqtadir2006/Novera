// Seeds the SQLite test database with ~30 days of random-but-plausible readings.
import { db, initSchema, countReadings } from "./db.js";

function mulberry32(seed) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const round = (v, dp) => {
  const f = 10 ** dp;
  return Math.round(v * f) / f;
};

function generate(days = 30) {
  const rand = mulberry32(Date.now() % 2 ** 31);
  const rows = [];
  const end = Date.now();
  const dayMs = 24 * 60 * 60 * 1000;

  for (let i = days - 1; i >= 0; i--) {
    const phase = (days - i) / days;
    const t = new Date(end - i * dayMs);
    t.setHours(9, 14, 0, 0);
    rows.push({
      timestamp: t.toISOString(),
      ph: round(6.7 + Math.sin(phase * 6) * 0.35 + (rand() - 0.5) * 0.25, 2),
      creatinine: round(0.95 + Math.sin(phase * 4 + 1) * 0.18 + (rand() - 0.5) * 0.12, 2),
      urea: round(18 + phase * 8 + Math.sin(phase * 5) * 3 + (rand() - 0.5) * 3, 1),
      temperature: round(36.8 + Math.sin(phase * 3) * 0.25 + (rand() - 0.5) * 0.2, 1),
    });
  }
  return rows;
}

function seed({ force = false } = {}) {
  initSchema();
  const existing = countReadings();
  if (existing > 0 && !force) {
    console.log(`DB already has ${existing} readings — skipping seed (use --force to reseed).`);
    return;
  }
  if (force) db.exec("DELETE FROM readings");

  const insert = db.prepare(
    "INSERT INTO readings (timestamp, ph, creatinine, urea, temperature) VALUES (?, ?, ?, ?, ?)"
  );
  const rows = generate(30);
  for (const r of rows) {
    insert.run(r.timestamp, r.ph, r.creatinine, r.urea, r.temperature);
  }
  console.log(`Seeded ${rows.length} readings into novera.db`);
}

const force = process.argv.includes("--force");
seed({ force });
