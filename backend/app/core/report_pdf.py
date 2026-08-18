"""Server-side PDF report generation — used to attach the screening report
to a WhatsApp message (req: "send the same report PDF that's on the
website, over WhatsApp").

IMPORTANT — this is a close visual match, not a byte-identical copy. The
website's PDF (frontend/src/components/reports/generateReportPdf.js) is a
`html2canvas` screenshot of the rendered `PrintableReport` DOM node dropped
into a jsPDF page — it needs a real browser to produce, which this backend
doesn't have. This module rebuilds the same content in the same order,
using the same brand colors/tokens and the same section layout
(PrintableReport in frontend/src/pages/Reports.jsx is the source of truth
for both), so it reads as the same report — just drawn with fpdf2's native
vector primitives instead of a screenshotted DOM. Deliberately English-only
for now: fpdf2's built-in fonts can't shape Arabic any more than jsPDF's
can without a browser, so callers should always pass an English-language
report_agent() result here, not silently attempt Arabic.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fpdf import FPDF

from . import fallbacks, reference_data

# fpdf2's core Helvetica/Courier fonts only support Latin-1 — no bundled
# Unicode TTF exists in this backend, and LLM-generated report text (this
# codebase's own writing style included) routinely contains em-dashes,
# curly quotes, and ellipses that would otherwise raise
# FPDFUnicodeEncodingException and crash PDF generation outright. Map the
# common offenders to Latin-1-safe equivalents, then replace anything still
# left outside Latin-1 rather than ever failing to produce a PDF.
_UNICODE_REPLACEMENTS = {
    "—": "-", "–": "-",       # em/en dash
    "‘": "'", "’": "'",       # curly single quotes
    "“": '"', "”": '"',       # curly double quotes
    "…": "...",                    # ellipsis
    "•": "-",                      # bullet
}


def _safe(text: Any) -> str:
    text = str(text or "")
    for bad, good in _UNICODE_REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", errors="replace").decode("latin-1")

# Same tokens as frontend/tailwind.config.js (theme.extend.colors) —
# keep in sync if the website's palette ever changes.
DEPTH = (18, 58, 92)       # heading/body text on light pages
SIGNAL = (63, 225, 214)    # primary accent (teal)
MIST = (234, 243, 251)     # light-blue page background
MIST_ALT_ROW = (240, 247, 253)  # ~mist/60, table zebra striping
SIGNAL_TINT = (237, 253, 251)   # ~signal/8, recommendation box background
MUTED = (130, 145, 160)    # ~depth/50-55, secondary text

STATUS_COLORS = {
    "good": (61, 220, 151),      # #3DDC97
    "watch": (242, 169, 62),     # #F2A93E
    "attention": (255, 93, 93),  # #FF5D5D
}


def _fmt_timestamp(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y, %H:%M UTC")
    except Exception:
        return ts


def build_report_pdf(reading: dict[str, Any], report_data: dict[str, Any]) -> bytes:
    """Returns raw PDF bytes for the given reading + report_agent() output.
    report_data is expected in English (see module docstring)."""
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(16, 16, 16)
    pdf.add_page()
    page_w = pdf.w - 2 * 16

    # ---- header: wordmark left, headline + timestamp right (mirrors the
    # PrintableReport flex header) ----
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*DEPTH)
    pdf.cell(page_w * 0.55, 9, "NOVERA", ln=0)

    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(*DEPTH)
    pdf.cell(page_w * 0.45, 6, _safe(report_data.get("headline", "")), ln=1, align="R")

    pdf.set_font("Courier", "", 8.5)
    pdf.set_text_color(*MUTED)
    pdf.set_x(pdf.l_margin + page_w * 0.55)
    pdf.cell(page_w * 0.45, 5, _fmt_timestamp(reading["timestamp"]), align="R")
    pdf.ln(10)

    pdf.set_draw_color(*SIGNAL)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + page_w, pdf.get_y())
    pdf.ln(6)

    # ---- overall summary ----
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*DEPTH)
    pdf.multi_cell(page_w, 6, _safe(report_data.get("overallSummary", "")))
    pdf.ln(4)

    # ---- biomarkers table ----
    pdf.set_font("Courier", "", 8.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(page_w, 5, "BIOMARKERS", ln=1)
    pdf.ln(1)

    col_w = [page_w * 0.30, page_w * 0.24, page_w * 0.26, page_w * 0.20]
    headers = ["Biomarker", "Value", "Reference", "Status"]
    pdf.set_fill_color(*DEPTH)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9.5)
    for w, h in zip(col_w, headers):
        pdf.cell(w, 8, h, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9.5)
    for i, key in enumerate(reference_data.REFERENCE):
        m = reading["metrics"][key]
        label = reference_data.REFERENCE[key]["label"]
        unit = f" {m['unit']}" if m.get("unit") else ""
        pdf.set_fill_color(*(MIST_ALT_ROW if i % 2 else (255, 255, 255)))
        pdf.set_text_color(*DEPTH)
        pdf.cell(col_w[0], 8, _safe(label), fill=True)
        pdf.cell(col_w[1], 8, _safe(f"{m['value']}{unit}"), fill=True)
        pdf.cell(col_w[2], 8, _safe(f"{m['range'][0]}-{m['range'][1]}{unit}"), fill=True)
        pdf.set_text_color(*STATUS_COLORS.get(m["status"], DEPTH))
        pdf.cell(col_w[3], 8, _safe(m["status"].upper()), fill=True)
        pdf.ln()
    pdf.ln(6)

    # ---- per-area summary (mirrors the mist-tinted card list) ----
    pdf.set_font("Courier", "", 8.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(page_w, 5, "AREA SUMMARY", ln=1)
    pdf.ln(1)

    for area in report_data.get("areas", []):
        area_name = _safe(area.get("name", ""))
        area_note = _safe(area.get("note", ""))
        area_status = _safe(area.get("status", "").upper())

        pdf.set_font("Helvetica", "", 9.5)
        note_lines = pdf.multi_cell(page_w - 6, 5, area_note, dry_run=True, output="LINES")
        card_h = 8 + 5 * len(note_lines) + 3
        # Draw the background rect first, then text on top — if that split
        # straddled a page break, the rect and text would land on different
        # pages. Force a fresh page up front instead when the card won't fit.
        if pdf.get_y() + card_h > pdf.page_break_trigger:
            pdf.add_page()
        card_top = pdf.get_y()

        pdf.set_fill_color(*MIST)
        pdf.rect(pdf.l_margin, card_top, page_w, card_h, style="F")

        pdf.set_xy(pdf.l_margin + 3, card_top + 2.5)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*DEPTH)
        pdf.cell(page_w * 0.6, 5, area_name)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(*STATUS_COLORS.get(area.get("status", ""), DEPTH))
        pdf.cell(page_w * 0.4 - 6, 5, area_status, align="R")

        pdf.set_xy(pdf.l_margin + 3, card_top + 7.5)
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*DEPTH)
        pdf.multi_cell(page_w - 6, 5, area_note)
        pdf.set_y(card_top + card_h + 3)

    # ---- recommendation (tinted callout box) ----
    if report_data.get("recommendation"):
        recommendation = _safe(report_data["recommendation"])
        pdf.set_font("Helvetica", "", 9.5)
        rec_lines = pdf.multi_cell(page_w - 8, 5, recommendation, dry_run=True, output="LINES")
        box_h = 5 * len(rec_lines) + 6
        if pdf.get_y() + box_h > pdf.page_break_trigger:
            pdf.add_page()
        box_top = pdf.get_y()
        pdf.set_fill_color(*SIGNAL_TINT)
        pdf.rect(pdf.l_margin, box_top, page_w, box_h, style="F")
        pdf.set_xy(pdf.l_margin + 4, box_top + 3)
        pdf.set_text_color(*DEPTH)
        pdf.multi_cell(page_w - 8, 5, recommendation)
        pdf.set_y(box_top + box_h + 5)
    else:
        pdf.ln(2)

    # ---- disclaimer ----
    pdf.set_draw_color(*SIGNAL)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + page_w, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(page_w, 4.5, _safe(report_data.get("disclaimer") or fallbacks.RESEARCH_LINE["en"]))

    return bytes(pdf.output())
