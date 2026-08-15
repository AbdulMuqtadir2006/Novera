"""Pydantic request bodies + agent-output models."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Lang = Literal["en", "ar"]

# ---- auth ----
class SignupReq(BaseModel):
    name: str = ""
    email: str
    password: str
    phone: str = ""


class LoginReq(BaseModel):
    email: str
    password: str


# ---- readings (dashboard) ----
class ReadingIn(BaseModel):
    ph: Optional[float] = None
    creatinine: Optional[float] = None
    urea: Optional[float] = None
    temperature: Optional[float] = None


# ---- ESP32 sensor node ----
class DevicePingIn(BaseModel):
    ssid: str = ""


# ---- patient context ----
class PatientContextIn(BaseModel):
    diagnosis: str = ""
    medications: str = ""
    notes: str = ""


# ---- content agents ----
class LangReq(BaseModel):
    lang: Lang = "en"


class SelfCareReq(BaseModel):
    lang: Lang = "en"
    # False (default): return the persisted plan if one exists — no LLM call.
    # True: always regenerate from scratch (and re-persist the result).
    force: bool = False


class ChatSendReq(BaseModel):
    message: str
    lang: Lang = "en"


# ---- appointments ----
class OfferReq(BaseModel):
    to: Optional[str] = None
    simulate: bool = True


class ReplyReq(BaseModel):
    message: str
    lang: Lang = "en"


# ---- agent output shapes (ported from the old novera_ai/schemas.py) ----
class ReportArea(BaseModel):
    id: str
    name: str
    status: str
    note: str


class ReportOut(BaseModel):
    headline: str
    overallSummary: str
    areas: list[ReportArea]
    recommendation: str


class DietPlan(BaseModel):
    breakfast: str
    lunch: str
    dinner: str
    snacks: str
    hydration: str


class AreaTip(BaseModel):
    id: str
    name: str
    status: str
    tip: str


class MealNutrition(BaseModel):
    meal: str
    calories: int = Field(ge=0, le=3000)
    protein_g: int = Field(ge=0, le=300)
    carbs_g: int = Field(ge=0, le=500)
    fat_g: int = Field(ge=0, le=300)
    micros: list[str] = []


class SelfCareOut(BaseModel):
    focusTitle: str
    focusBody: str
    dietPlan: DietPlan
    areaTips: list[AreaTip]
    nutrition: list[MealNutrition] = []


class VoiceOut(BaseModel):
    script: str = Field(min_length=10)


class ChatOut(BaseModel):
    reply: str
    diagnosis: str = ""
    medications: str = ""
    notes: str = ""
    contextChanged: bool = False


# ---- screening (organ prediction) ----
class FinalDecision(BaseModel):
    """The only output accepted from the OpenRouter screening decision call."""

    prediction: Literal["KIDNEY", "STOMACH", "ORAL"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=15, max_length=600)


# ---- WhatsApp appointment reply understanding ----
class AppointmentReplyIntent(BaseModel):
    intent: Literal["confirm", "decline", "reschedule", "question", "unknown"]
    note: str = ""


class WhatsAppQAAnswer(BaseModel):
    reply: str = Field(min_length=1, max_length=1200)
