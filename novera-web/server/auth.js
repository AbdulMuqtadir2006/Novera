// Demo-grade auth: scrypt password hashing + opaque session tokens in SQLite.
// (Sufficient for a research/demo app; not a hardened production auth system.)
import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";
import { db } from "./db.js";

function hashPassword(password) {
  const salt = randomBytes(16).toString("hex");
  const hash = scryptSync(password, salt, 64).toString("hex");
  return { salt, hash };
}

function verifyPassword(password, salt, expectedHash) {
  const hash = scryptSync(password, salt, 64);
  const expected = Buffer.from(expectedHash, "hex");
  return hash.length === expected.length && timingSafeEqual(hash, expected);
}

// Normalise a phone to "+<digits>" (defaults to Oman +968 when no country code).
export function normalizePhone(raw) {
  if (!raw) return "";
  const hadPlus = String(raw).trim().startsWith("+");
  let digits = String(raw).replace(/\D/g, "");
  if (digits.startsWith("00")) digits = digits.slice(2); // 00 = international prefix
  if (hadPlus) return "+" + digits;
  if (digits.startsWith("968")) return "+" + digits; // already has Oman country code
  digits = digits.replace(/^0+/, ""); // trailing local 0
  if (digits.length <= 9) return "+968" + digits; // bare Oman local number
  return "+" + digits; // some other international number
}

function publicUser(row) {
  if (!row) return null;
  return { id: row.id, email: row.email, name: row.name, phone: row.phone };
}

export function createUser({ name = "", email, password, phone }) {
  const normEmail = String(email || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(normEmail)) throw new Error("Invalid email");
  if (!password || password.length < 6) throw new Error("Password must be at least 6 characters");
  const normPhone = normalizePhone(phone);
  if (!/^\+\d{8,15}$/.test(normPhone)) throw new Error("Invalid phone number (include country code, e.g. +968...)");

  const existing = db.prepare("SELECT id FROM users WHERE email = ?").get(normEmail);
  if (existing) throw new Error("An account with this email already exists");

  const { salt, hash } = hashPassword(password);
  const info = db
    .prepare(
      "INSERT INTO users (email, name, phone, pass_salt, pass_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)"
    )
    .run(normEmail, name.trim(), normPhone, salt, hash, new Date().toISOString());
  return publicUser(db.prepare("SELECT * FROM users WHERE id = ?").get(info.lastInsertRowid));
}

export function authenticate(email, password) {
  const row = db.prepare("SELECT * FROM users WHERE email = ?").get(String(email || "").trim().toLowerCase());
  if (!row) return null;
  if (!verifyPassword(password, row.pass_salt, row.pass_hash)) return null;
  return publicUser(row);
}

export function createSession(userId) {
  const token = randomBytes(32).toString("hex");
  db.prepare("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)").run(
    token,
    userId,
    new Date().toISOString()
  );
  return token;
}

export function getUserByToken(token) {
  if (!token) return null;
  const row = db
    .prepare(
      "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?"
    )
    .get(token);
  return publicUser(row);
}

export function deleteSession(token) {
  if (token) db.prepare("DELETE FROM sessions WHERE token = ?").run(token);
}

// Express middleware — attaches req.user if a valid Bearer token is present.
export function attachUser(req, _res, next) {
  const auth = req.headers.authorization || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : null;
  req.token = token;
  req.user = getUserByToken(token);
  next();
}

export function requireAuth(req, res, next) {
  if (!req.user) return res.status(401).json({ error: "Not authenticated" });
  next();
}
