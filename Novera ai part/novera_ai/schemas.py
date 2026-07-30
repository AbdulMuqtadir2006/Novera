"""Pydantic models for agent outputs and API payloads."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Lang = Literal["en", "ar"]
AreaId = Literal["kidney", "hydration", "oral", "digestive"]

METRIC_KEYS = ("ph", "creatinine", "urea", "temperature")


# ---- incoming reading (web app shape) ----
class Metric(BaseModel):
    value: float
    unit: str = ""
    range: list[float]
    status: str


class Reading(BaseModel):
    timestamp: str
    metrics: dict[str, Metric]
    healthAreas: dict[str, str]


class PatientContext(BaseModel):
    diagnosis: str = ""
    medications: str = ""
    notes: str = ""


class ChatMessage(BaseModel):
    role: str
    content: str


# ---- agent outputs ----
class VoiceOut(BaseModel):
    script: str = Field(min_length=10)


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
    meal: str  # breakfast | lunch | dinner | snacks
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


class ChatOut(BaseModel):
    reply: str
    diagnosis: str = ""
    medications: str = ""
    notes: str = ""
    contextChanged: bool = False


# ---- appointment agent ----
class AppointmentReplyIntent(BaseModel):
    """LLM understanding of a free-text WhatsApp reply."""
    intent: Literal["confirm", "decline", "reschedule", "question", "unknown"]
    clinic: Optional[str] = None
    note: str = ""
