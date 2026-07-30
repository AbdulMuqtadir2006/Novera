// AI client — delegates all generation to the Python agentic service
// (LangGraph + OpenRouter). If the service is unreachable, falls back to
// deterministic bilingual output so the app never breaks.
import { REFERENCE } from "./health.js";

const AI_URL = process.env.AI_SERVICE_URL || "http://127.0.0.1:8000";
export const aiEnabled = true; // real status is reported via serviceHealth()

async function aiPost(path, body, timeoutMs = 60000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${AI_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(`AI service ${path} -> ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

async function aiGet(path, timeoutMs = 15000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${AI_URL}${path}`, { signal: ctrl.signal });
    if (!res.ok) throw new Error(`AI service ${path} -> ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

export async function serviceHealth() {
  try {
    return await aiGet("/health");
  } catch {
    return { ok: false, ai_enabled: false, reachable: false };
  }
}

// ---- content agents (proxy + fallback) ----
export async function generateVoiceScript(reading, lang = "en") {
  try {
    return await aiPost("/ai/voice", { reading, lang });
  } catch (e) {
    console.error("voice proxy error:", e.message);
    return fallbackVoice(reading, lang);
  }
}

export async function generateReport(reading, ctx, lang = "en") {
  try {
    return await aiPost("/ai/report", { reading, context: ctx, lang });
  } catch (e) {
    console.error("report proxy error:", e.message);
    return fallbackReport(reading, lang);
  }
}

export async function generateSelfCare(reading, ctx, chatHistory, lang = "en") {
  try {
    return await aiPost("/ai/self-care", { reading, context: ctx, chat: chatHistory || [], lang });
  } catch (e) {
    console.error("selfcare proxy error:", e.message);
    return fallbackSelfCare(reading, lang);
  }
}

export async function chat(messages, reading, ctx, lang = "en") {
  try {
    return await aiPost("/ai/chat", { messages, reading, context: ctx, lang }, 60000);
  } catch (e) {
    console.error("chat proxy error:", e.message);
    return fallbackChat(messages, ctx, lang);
  }
}

// ---- agentic extras ----
export async function predictOrgan(reading) {
  return aiPost("/ai/predict-organ", { reading }, 60000);
}
export async function appointmentOffer(payload) {
  return aiPost("/appointment/offer", payload || {}, 30000);
}
export async function appointmentReply(message, lang = "en") {
  return aiPost("/appointment/reply", { message, lang }, 60000);
}
export async function listBookings() {
  return aiGet("/appointment/bookings");
}
export async function getClinic() {
  return aiGet("/clinic");
}
// Full agentic LangGraph pipeline (orchestrator).
export async function runPipeline(reading) {
  return aiPost("/orchestrator/run", { user_id: "demo-user", raw_reading: reading }, 120000);
}
export async function orchestratorWhatsApp(message) {
  return aiPost("/orchestrator/whatsapp", { user_id: "demo-user", message }, 90000);
}

// ---- deterministic fallbacks (service unreachable) ----
const AREA_NAMES = {
  en: { kidney: "Kidney Health", hydration: "Hydration", oral: "Oral Health", digestive: "Digestive Health" },
  ar: { kidney: "صحة الكلى", hydration: "الترطيب", oral: "صحة الفم", digestive: "صحة الجهاز الهضمي" },
};
const STATUS_WORD = {
  en: { good: "in range", watch: "worth watching", attention: "needs attention" },
  ar: { good: "ضمن المعدل", watch: "تستحق المتابعة", attention: "تحتاج انتباهاً" },
};
const RESEARCH_LINE = {
  en: "Novera is a research-stage screening platform — not a diagnostic device. This is a screening summary, not medical advice.",
  ar: "نوفيرا منصة فحص في مرحلة بحثية وليست جهاز تشخيص. هذا ملخص فحص وليس نصيحة طبية.",
};

function fallbackVoice(reading, lang) {
  const names = AREA_NAMES[lang] || AREA_NAMES.en;
  const sw = STATUS_WORD[lang] || STATUS_WORD.en;
  const watch = Object.entries(reading.healthAreas).filter(([, s]) => s !== "good").map(([a]) => names[a]);
  const parts = Object.keys(REFERENCE).map((k) => {
    const m = reading.metrics[k];
    return lang === "ar"
      ? `${REFERENCE[k].label} بقيمة ${m.value} وهي ${sw[m.status]}`
      : `${REFERENCE[k].label} reads ${m.value}, which is ${sw[m.status]}`;
  });
  const script =
    lang === "ar"
      ? `إليك ملخص الفحص الخاص بك من نوفيرا. هذا ملخص في مرحلة بحثية وليس تشخيصاً طبياً. عبر مؤشراتك الأربعة: ${parts.join("، ")}. ${watch.length ? `المجالات التي تستحق نظرة أقرب هي: ${watch.join("، ")}.` : "جميع مجالاتك الصحية تبدو مستقرة."} تذكّر أن نوفيرا مصممة لاستكشاف ما يخبرنا به اللعاب، ولأي أمر يقلقك راجع أخصائياً طبياً.`
      : `Here's your Novera screening summary. This is a research-stage overview, not a medical diagnosis. Across your four biomarkers: ${parts.join(", ")}. ${watch.length ? `The areas worth a closer look are: ${watch.join(", ")}.` : "All of your health areas look steady."} Remember, Novera is built to explore what saliva can tell us — for anything concerning, check with a medical professional.`;
  return { script, source: "fallback" };
}

function fallbackReport(reading, lang) {
  const names = AREA_NAMES[lang] || AREA_NAMES.en;
  const sw = STATUS_WORD[lang] || STATUS_WORD.en;
  const areas = Object.entries(reading.healthAreas).map(([id, status]) => ({
    id,
    name: names[id],
    status,
    note: lang === "ar" ? `${names[id]}: المؤشرات ${sw[status]} في هذه القراءة.` : `${names[id]}: markers are ${sw[status]} for this reading.`,
  }));
  return {
    headline: lang === "ar" ? "ملخص الفحص" : "Screening Summary",
    overallSummary:
      lang === "ar"
        ? "ملخص بلغة واضحة لأحدث قراءة لعاب، عبر أربعة مجالات صحية."
        : "A plain-language summary of your latest saliva reading across four health areas.",
    areas,
    recommendation:
      lang === "ar"
        ? "حافظ على ترطيب منتظم ونظام غذائي متوازن، وراجع أخصائياً طبياً لأي مؤشر مستمر خارج المعدل."
        : "Keep a steady fluid intake and a balanced diet, and consult a professional for any signal that stays out of range.",
    disclaimer: RESEARCH_LINE[lang] || RESEARCH_LINE.en,
    source: "fallback",
  };
}

function fallbackSelfCare(reading, lang) {
  const names = AREA_NAMES[lang] || AREA_NAMES.en;
  const sw = STATUS_WORD[lang] || STATUS_WORD.en;
  const RANK = { good: 0, watch: 1, attention: 2 };
  const focus = Object.entries(reading.healthAreas).sort((a, b) => RANK[b[1]] - RANK[a[1]])[0];
  const areaTips = Object.entries(reading.healthAreas).map(([id, status]) => ({
    id,
    name: names[id],
    status,
    tip: lang === "ar" ? `${names[id]}: المؤشرات ${sw[status]}. حافظ على عادات متوازنة.` : `${names[id]}: markers are ${sw[status]}. Keep balanced habits.`,
  }));
  return {
    focusTitle: lang === "ar" ? `تركيز اليوم: ${names[focus[0]]}` : `Today's focus: ${names[focus[0]]}`,
    focusBody:
      lang === "ar"
        ? "خطة عامة للعناية الذاتية مبنية على قراءتك الأخيرة. أضف سياق طبيبك في المحادثة لتخصيصها."
        : "A general self-care plan based on your latest reading. Share your doctor's context in the chat to personalise it.",
    dietPlan:
      lang === "ar"
        ? { breakfast: "شوفان بالماء مع فاكهة.", lunch: "أرز بني مع خضار وبروتين خفيف.", dinner: "شوربة عدس مع سلطة.", snacks: "مكسرات غير مملحة وفاكهة.", hydration: "٦–٨ أكواب ماء في اليوم." }
        : { breakfast: "Oats with fresh fruit.", lunch: "Brown rice with vegetables and a light protein.", dinner: "Lentil soup with salad.", snacks: "Unsalted nuts and fruit.", hydration: "6–8 glasses of water a day." },
    areaTips,
    source: "fallback",
  };
}

function fallbackChat(messages, ctx, lang) {
  const last = messages[messages.length - 1]?.content || "";
  const notes = [ctx.notes, last].filter(Boolean).join(" | ");
  return {
    reply:
      lang === "ar"
        ? "شكراً لمشاركتك هذا. سجّلت ملاحظاتك وسأضعها في اعتباري. (الخدمة غير متصلة حالياً.)"
        : "Thanks for sharing that. I've noted it and will factor it into your plan. (AI service offline.)",
    diagnosis: ctx.diagnosis || "",
    medications: ctx.medications || "",
    notes,
    contextChanged: !!last,
    source: "fallback",
  };
}
