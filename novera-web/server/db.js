import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DB_PATH = join(__dirname, "novera.db");

export const db = new DatabaseSync(DB_PATH);

export function initSchema() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS readings (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp   TEXT    NOT NULL,
      ph          REAL    NOT NULL,
      creatinine  REAL    NOT NULL,
      urea        REAL    NOT NULL,
      temperature REAL    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS patient_context (
      id          INTEGER PRIMARY KEY CHECK (id = 1),
      diagnosis   TEXT    DEFAULT '',
      medications TEXT    DEFAULT '',
      notes       TEXT    DEFAULT '',
      updated_at  TEXT
    );

    CREATE TABLE IF NOT EXISTS chat_messages (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      role       TEXT    NOT NULL,
      content    TEXT    NOT NULL,
      lang       TEXT    DEFAULT 'en',
      created_at TEXT    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS users (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      email      TEXT    NOT NULL UNIQUE,
      name       TEXT    DEFAULT '',
      phone      TEXT    DEFAULT '',
      pass_salt  TEXT    NOT NULL,
      pass_hash  TEXT    NOT NULL,
      created_at TEXT    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sessions (
      token      TEXT    PRIMARY KEY,
      user_id    INTEGER NOT NULL,
      created_at TEXT    NOT NULL,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
  `);

  // Ensure the singleton patient_context row exists.
  const row = db.prepare("SELECT id FROM patient_context WHERE id = 1").get();
  if (!row) {
    db.prepare(
      "INSERT INTO patient_context (id, diagnosis, medications, notes, updated_at) VALUES (1, '', '', '', ?)"
    ).run(new Date().toISOString());
  }
}

export function countReadings() {
  return db.prepare("SELECT COUNT(*) AS c FROM readings").get().c;
}
