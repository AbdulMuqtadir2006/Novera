"""Deterministic bilingual fallbacks used when OpenRouter is unavailable.

Ported 1:1 from the old novera_ai/fallbacks.py (the JS copy in the Node
backend is retired — this is now the single source).
"""
from __future__ import annotations

from typing import Any

REFERENCE_LABELS = {"ph": "pH", "creatinine": "Creatinine", "urea": "Urea", "temperature": "Temperature"}
METRIC_KEYS = ("ph", "creatinine", "urea", "temperature")

RESEARCH_LINE = {
    "en": "Novera is a research-stage screening platform — not a diagnostic device. This is a screening summary, not medical advice.",
    "ar": "نوفيرا منصة فحص في مرحلة بحثية وليست جهاز تشخيص. هذا ملخص فحص وليس نصيحة طبية.",
}
AREA_NAMES = {
    "en": {"kidney": "Kidney Health", "hydration": "Hydration", "oral": "Oral Health", "digestive": "Digestive Health"},
    "ar": {"kidney": "صحة الكلى", "hydration": "الترطيب", "oral": "صحة الفم", "digestive": "صحة الجهاز الهضمي"},
}
STATUS_WORD = {
    "en": {"good": "in range", "watch": "worth watching", "attention": "needs attention"},
    "ar": {"good": "ضمن المعدل", "watch": "تستحق المتابعة", "attention": "تحتاج انتباهاً"},
}


def _val(reading: dict[str, Any], key: str) -> Any:
    return reading["metrics"][key]["value"]


def voice(reading: dict[str, Any], lang: str) -> dict[str, Any]:
    sw = STATUS_WORD.get(lang, STATUS_WORD["en"])
    names = AREA_NAMES.get(lang, AREA_NAMES["en"])
    watch = [names[a] for a, s in reading["healthAreas"].items() if s != "good"]
    if lang == "ar":
        parts = [f"{REFERENCE_LABELS[k]} بقيمة {_val(reading,k)} وهي {sw[reading['metrics'][k]['status']]}" for k in METRIC_KEYS]
        watch_txt = f"المجالات التي تستحق نظرة أقرب هي: {'، '.join(watch)}." if watch else "جميع مجالاتك الصحية تبدو مستقرة."
        script = (
            "إليك ملخص الفحص الخاص بك من نوفيرا. هذا ملخص في مرحلة بحثية وليس تشخيصاً طبياً. "
            f"عبر مؤشراتك الأربعة: {'، '.join(parts)}. {watch_txt} "
            "تذكّر أن نوفيرا مصممة لاستكشاف ما يخبرنا به اللعاب، ولأي أمر يقلقك راجع أخصائياً طبياً."
        )
    else:
        parts = [f"{REFERENCE_LABELS[k]} reads {_val(reading,k)}, which is {sw[reading['metrics'][k]['status']]}" for k in METRIC_KEYS]
        watch_txt = f"The areas worth a closer look are: {', '.join(watch)}." if watch else "All of your health areas look steady."
        script = (
            "Here's your Novera screening summary. This is a research-stage overview, not a medical diagnosis. "
            f"Across your four biomarkers: {', '.join(parts)}. {watch_txt} "
            "Remember, Novera is built to explore what saliva can tell us — for anything concerning, check with a medical professional."
        )
    return {"script": script, "source": "fallback"}


def report(reading: dict[str, Any], lang: str) -> dict[str, Any]:
    sw = STATUS_WORD.get(lang, STATUS_WORD["en"])
    names = AREA_NAMES.get(lang, AREA_NAMES["en"])
    areas = [
        {
            "id": aid,
            "name": names[aid],
            "status": status,
            "note": (
                f"{names[aid]}: المؤشرات {sw[status]} في هذه القراءة." if lang == "ar"
                else f"{names[aid]}: markers are {sw[status]} for this reading."
            ),
        }
        for aid, status in reading["healthAreas"].items()
    ]
    return {
        "headline": "ملخص الفحص" if lang == "ar" else "Screening Summary",
        "overallSummary": (
            "ملخص بلغة واضحة لأحدث قراءة لعاب، عبر أربعة مجالات صحية." if lang == "ar"
            else "A plain-language summary of your latest saliva reading across four health areas."
        ),
        "areas": areas,
        "recommendation": (
            "حافظ على ترطيب منتظم ونظام غذائي متوازن، وراجع أخصائياً طبياً لأي مؤشر مستمر خارج المعدل." if lang == "ar"
            else "Keep a steady fluid intake and a balanced diet, and consult a professional for any signal that stays out of range."
        ),
        "disclaimer": RESEARCH_LINE.get(lang, RESEARCH_LINE["en"]),
        "source": "fallback",
    }


def self_care(reading: dict[str, Any], lang: str) -> dict[str, Any]:
    sw = STATUS_WORD.get(lang, STATUS_WORD["en"])
    names = AREA_NAMES.get(lang, AREA_NAMES["en"])
    rank = {"good": 0, "watch": 1, "attention": 2}
    focus = max(reading["healthAreas"].items(), key=lambda kv: rank[kv[1]])
    area_tips = [
        {
            "id": aid,
            "name": names[aid],
            "status": status,
            "tip": (
                f"{names[aid]}: المؤشرات {sw[status]}. حافظ على عادات متوازنة وتابع في القراءة القادمة." if lang == "ar"
                else f"{names[aid]}: markers are {sw[status]}. Keep balanced habits and review at your next reading."
            ),
        }
        for aid, status in reading["healthAreas"].items()
    ]
    diet = (
        {
            "breakfast": "شوفان بالماء مع فاكهة طازجة وكوب ماء.",
            "lunch": "أرز بني مع خضار مشوية وبروتين خفيف.",
            "dinner": "شوربة عدس خفيفة مع سلطة.",
            "snacks": "مكسرات غير مملحة وفاكهة.",
            "hydration": "٦–٨ أكواب ماء موزعة على اليوم.",
        }
        if lang == "ar"
        else {
            "breakfast": "Oats with fresh fruit and a glass of water.",
            "lunch": "Brown rice with roasted vegetables and a light protein.",
            "dinner": "A light lentil soup with salad.",
            "snacks": "Unsalted nuts and fruit.",
            "hydration": "6–8 glasses of water spread across the day.",
        }
    )
    if lang == "ar":
        nutrition = [
            {"meal": "breakfast", "calories": 320, "protein_g": 12, "carbs_g": 52, "fat_g": 7, "micros": ["غني بالألياف", "فيتامين C"]},
            {"meal": "lunch", "calories": 520, "protein_g": 26, "carbs_g": 68, "fat_g": 14, "micros": ["منخفض الصوديوم", "حديد"]},
            {"meal": "dinner", "calories": 410, "protein_g": 20, "carbs_g": 55, "fat_g": 10, "micros": ["غني بالبوتاسيوم", "ألياف"]},
            {"meal": "snacks", "calories": 210, "protein_g": 7, "carbs_g": 22, "fat_g": 12, "micros": ["دهون صحية", "مغنيسيوم"]},
        ]
    else:
        nutrition = [
            {"meal": "breakfast", "calories": 320, "protein_g": 12, "carbs_g": 52, "fat_g": 7, "micros": ["High in fibre", "Vitamin C"]},
            {"meal": "lunch", "calories": 520, "protein_g": 26, "carbs_g": 68, "fat_g": 14, "micros": ["Lower sodium", "Iron"]},
            {"meal": "dinner", "calories": 410, "protein_g": 20, "carbs_g": 55, "fat_g": 10, "micros": ["Rich in potassium", "Fibre"]},
            {"meal": "snacks", "calories": 210, "protein_g": 7, "carbs_g": 22, "fat_g": 12, "micros": ["Healthy fats", "Magnesium"]},
        ]
    return {
        "focusTitle": (f"تركيز اليوم: {names[focus[0]]}" if lang == "ar" else f"Today's focus: {names[focus[0]]}"),
        "focusBody": (
            "خطة عامة للعناية الذاتية مبنية على قراءتك الأخيرة. أضف سياق طبيبك في المحادثة لتخصيصها أكثر." if lang == "ar"
            else "A general self-care plan based on your latest reading. Share your doctor's context in the chat to personalise it further."
        ),
        "dietPlan": diet,
        "areaTips": area_tips,
        "nutrition": nutrition,
        "source": "fallback",
    }


def chat(messages: list[dict[str, Any]], ctx: dict[str, Any], lang: str) -> dict[str, Any]:
    last = messages[-1]["content"] if messages else ""
    notes = " | ".join([p for p in [ctx.get("notes", ""), last] if p])
    return {
        "reply": (
            "شكراً لمشاركتك هذا. سجّلت ملاحظاتك وسأضعها في اعتباري عند تحديث خطة العناية الذاتية. (وضع بديل بدون اتصال بالذكاء الاصطناعي.)" if lang == "ar"
            else "Thanks for sharing that. I've noted it and will factor it into your self-care plan. (Offline fallback — no AI key active.)"
        ),
        "diagnosis": ctx.get("diagnosis", ""),
        "medications": ctx.get("medications", ""),
        "notes": notes,
        "contextChanged": bool(last),
        "source": "fallback",
    }
