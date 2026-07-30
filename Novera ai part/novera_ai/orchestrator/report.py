"""Report Agent — compiles the screening into a downloadable PDF (brief §6.8).

Uses ReportLab. English labels; the AI insight/guidance text is embedded as-is.
(Arabic glyph shaping in the PDF is a follow-up alongside the TTS/API-key work.)
"""
from __future__ import annotations

from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .. import config
from .state import DISCLAIMER, REFERENCE

REPORTS_DIR = config.PROJECT_ROOT / "novera_ai" / "orchestrator" / "reports"
INK = colors.HexColor("#080919")
DEPTH = colors.HexColor("#241A44")
CYAN = colors.HexColor("#28CFE0")
MAGENTA = colors.HexColor("#EC61E8")
STATUS_COLORS = {"normal": colors.HexColor("#22a06b"), "watch": colors.HexColor("#c98a1a"), "concern": colors.HexColor("#d64545")}


def build_report_pdf(state: dict[str, Any]) -> str:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rid = state.get("reading_id", "reading")
    path = REPORTS_DIR / f"novera-{rid}.pdf"

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=DEPTH, fontSize=20)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=DEPTH, fontSize=13, spaceBefore=10)
    body = ParagraphStyle("body", parent=styles["Normal"], textColor=DEPTH, fontSize=10, leading=15)
    small = ParagraphStyle("small", parent=styles["Normal"], textColor=colors.HexColor("#6b6480"), fontSize=8, leading=12)

    ctx = state.get("user_context", {})
    reading = state.get("raw_reading", {})
    analysis = state.get("analysis_results", {})

    doc = SimpleDocTemplate(str(path), pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm, title="Novera Screening Report")
    story = []

    story.append(Paragraph("NOVERA — Screening Report", h1))
    story.append(Paragraph(f"{ctx.get('name','')}  ·  generated {__import__('datetime').datetime.now():%d %b %Y, %H:%M}", small))
    story.append(Spacer(1, 8))

    # Biomarker table
    story.append(Paragraph("Biomarker readings", h2))
    rows = [["Biomarker", "Value", "Reference"]]
    labels = {"ph": "pH", "creatinine": "Creatinine", "urea": "Urea", "temperature": "Temperature"}
    for k in ("ph", "creatinine", "urea", "temperature"):
        ref = REFERENCE[k]
        unit = f" {ref['unit']}" if ref["unit"] else ""
        rows.append([labels[k], f"{reading.get(k, '—')}{unit}", f"{ref['range'][0]}–{ref['range'][1]}{unit}"])
    tbl = Table(rows, colWidths=[55 * mm, 55 * mm, 55 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DEPTH),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f0fb")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9d3ec")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl)

    # Analysis per health area
    story.append(Paragraph("Health area analysis", h2))
    a_rows = [["Health area", "Status", "Severity", "Key finding"]]
    for area, data in analysis.items():
        a_rows.append([area, str(data.get("status", "")), str(data.get("severity", "")), Paragraph(str(data.get("key_finding", "")), small)])
    a_tbl = Table(a_rows, colWidths=[35 * mm, 22 * mm, 20 * mm, 88 * mm])
    a_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DEPTH),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9d3ec")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(a_tbl)

    if state.get("threshold_crossed"):
        story.append(Spacer(1, 6))
        story.append(Paragraph("⚠ A clinical threshold was crossed — professional follow-up is recommended.",
                               ParagraphStyle("warn", parent=body, textColor=STATUS_COLORS["concern"])))

    # Insight + guidance
    if state.get("insight_text"):
        story.append(Paragraph("What this means", h2))
        story.append(Paragraph(state["insight_text"].replace("\n", "<br/>"), body))
    if state.get("guidance_plan"):
        story.append(Paragraph("Your self-care plan", h2))
        story.append(Paragraph(state["guidance_plan"].replace("\n", "<br/>"), body))

    story.append(Spacer(1, 14))
    story.append(Paragraph(DISCLAIMER, small))

    doc.build(story)
    return str(path)
