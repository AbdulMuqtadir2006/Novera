# Novera — Pitch Addendum: Responding to the Judging Panel

**Status:** Response document. Last updated 2026-08-11.
**Read time:** ~5 minutes.

Novera was evaluated by a government-linked AI engineering panel and scored 2.54/5 (≈50.75%,
weighted), with Technical Product (1.5/5) and AI Safety, Ethics & Oversight (1.75/5) as the two
weakest areas. This document answers every judge comment and recommendation directly, point by point,
citing the specific artifact that backs each response. Nothing here is a promise — each answer points
to a document, a section of code, or a live part of the product a judge can go check themselves.

The three artifacts referenced throughout:

1. [`REGULATORY_AND_CLINICAL_PATHWAY.md`](./REGULATORY_AND_CLINICAL_PATHWAY.md) — the clinical
   validation and medical-device licensing route.
2. [`DATA_PRIVACY_AND_SAFETY.md`](./DATA_PRIVACY_AND_SAFETY.md) — the AI safety architecture and an
   honest account of current data-privacy gaps.
3. The **Trust & Transparency section**, now live on the homepage — no login required, scroll to the
   section titled "How Novera keeps its AI honest" (`frontend/src/components/home/
   TrustTransparencySection.jsx`).

---

## Score summary being addressed

| Criterion | Weight | Score | Judge's core concern |
|---|---|---|---|
| Impact & Business Viability | 25% | 3.0/5 | — |
| Relevance & Innovation | 20% | 3.75/5 | — |
| Technical Product | 25% | **1.5/5** | No device demo, hardware unbuilt, biomarkers unclear |
| Team & Future Plans | 10% | 2.5/5 | No clinical/regulatory plan |
| AI Safety, Ethics & Oversight | 15% | 1.75/5 | Health-data handling not addressed |
| Pitch Quality | 5% | 3.0/5 | — |
| **Weighted total** | | **≈2.54/5 (50.75%)** | |

---

## Judge comment: "The hardware is not built, no device or app demo was shown, so every accuracy claim is hypothetical."

**What we're doing about it.** We are not disputing this — it is accurate, and the
`REGULATORY_AND_CLINICAL_PATHWAY.md` document says so in its own opening section ("Honest current-state
summary"): the ESP32 firmware currently generates randomized values in a plausible range, not real
chemistry. We have removed every implicit claim of hardware readiness from our materials and replaced
it with a phased plan (`TEAM_AND_ROADMAP.md`, Section 2) that treats real sensor integration as the
first, unstarted milestone — with the concrete fact that the firmware's own code comments (`hardware/
esp32_sensor/esp32_sensor.ino`, lines 11–27) document exactly where the real sensor reads plug in, and
that doing so requires **zero changes** to the backend, scoring engine, or frontend, because the
interface is already fixed at four floating-point values over HTTP. This narrows what remains to a
hardware-sourcing and firmware problem, not a redesign.

What **is** demoable today without hardware: the WhatsApp booking flow (see the recommendation on
agentic AI, below) and the full screening-decision pipeline, which can run end-to-end against any
reading in the database — dummy or real — since the scoring and decision logic doesn't know or care
where the number came from. We are not claiming this substitutes for a hardware demo; we are stating
precisely what our software demo does and doesn't prove.

---

## Judge comment: "What the device actually measures was unclear."

**What we're doing about it.** Stated precisely: **four biomarkers** — pH, creatinine, urea, and
temperature — mapped to four health areas: oral, kidney, hydration, and digestive health respectively.
This mapping is now explicit in `REGULATORY_AND_CLINICAL_PATHWAY.md` Section 6 (index test definition)
and drives the scoring engine's three candidate organ categories (KIDNEY, STOMACH, ORAL). There is no
ambiguity left in what the sensor package is intended to measure — only in whether the physical sensors
exist yet to measure it (they don't; see above).

---

## Judge recommendation: "Demonstrate the device live; if comparable hardware exists, validate against its data."

**What we're doing about it.** No comparable hardware exists yet, and we are not claiming otherwise.
`TEAM_AND_ROADMAP.md` Section 2 lists real sensor sourcing and integration as the top near-term,
no-funding-required action item. `REGULATORY_AND_CLINICAL_PATHWAY.md` Phase 1 (Section 7) defines the
gate this must pass before any clinical work starts: device readings verified against certified
reference solutions/standards, independent of the software. We would rather present this as a named,
gated next step than simulate a demo that misrepresents where the hardware actually is.

---

## Judge recommendation: "Provide accuracy evidence against traditional blood tests on a larger dataset, and involve medical professionals."

**What we're doing about it.** `REGULATORY_AND_CLINICAL_PATHWAY.md` Section 6 lays out a concrete,
STARD-2015-aligned diagnostic accuracy study design: Novera's saliva readings as the index test, a
paired venous blood-test panel (serum creatinine/eGFR and BUN for the kidney pathway, defined jointly
with a partner clinician) as the reference standard, a pilot cohort on the order of 50–100 participants,
and sensitivity/specificity/PPV/NPV/Cohen's kappa as the reported metrics. Critically, "involve medical
professionals" is not a future aspiration bolted onto this design — the study explicitly requires a
named clinical lead to adjudicate every reference-standard outcome before it is entered as ground truth
(Section 6, "Oversight"), and `TEAM_AND_ROADMAP.md` Section 5 lists a clinician/medical advisor as a
required role starting in the 3–6 month phase.

We are not presenting accuracy numbers today because none exist on real data yet — and we would rather
say that plainly than assert a number we can't back with a dataset.

---

## Judge recommendation: "Define the regulatory pathway: clinical trials and medical-device licensing."

**What we're doing about it.** This is the single most complete gap this response effort closes.
`REGULATORY_AND_CLINICAL_PATHWAY.md` provides:

- A risk-classification analysis against IMDRF/GHTF, EU IVDR, and US FDA frameworks (Section 2),
  concluding Novera's triage-not-diagnosis, human-handoff design argues for a low risk class, while
  being explicit about where it does *not* qualify for exemptions (e.g., it would likely fail the US
  CDS carve-out's criterion 1, since a biosensor reading is an IVD signal).
- Oman's actual regulatory structure (Section 3): the DGPA&DC Medical Device Control Department, its
  four-tier classification, the July 2025 Circular 161/2025 electronic registration portal, and Oman's
  RERAC/HSRAC ethics-approval bodies for any human-subjects pilot — with an explicit list of what is
  **not** yet publicly confirmed and needs a direct answer from Oman MOH (e.g., software/SaMD-specific
  classification), rather than guessed.
- The international standards track (Section 4): ISO 13485, IEC 62304, ISO 14971, IEC 62366-1.
- A four-phase gated pathway (Section 7) from today's synthetic-data-only state through sensor bench
  validation, clinical concordance, to formal regulatory submission — with `TEAM_AND_ROADMAP.md`
  Sections 3–4 attaching concrete timeframes (3–6 months, 6–18 months) to each phase.

---

## Judge recommendation: "Demonstrate at least one agentic AI feature in the app, and address health-data privacy."

**What we're doing about it — agentic AI.** The WhatsApp booking flow is Novera's clearest agentic
behavior and is demoable today with nothing more than a reading in the database (real or dummy): a
LangGraph state machine classifies patient intent and branches into book / decline / reschedule /
answer-from-facts paths, with deterministic slot-finding backed by a database uniqueness constraint
(`UNIQUE (slot_start)`) that prevents double-booking even under concurrent requests
(`DATA_PRIVACY_AND_SAFETY.md` §1.5). The organ-screening pipeline itself is also agentic in a narrower,
safety-relevant sense: deterministic scoring feeds a single constrained LLM decision call, with a hard
rule that a failed or invalid call **never** produces a fabricated result (§1.1) — this is now visible
on the homepage's Trust & Transparency section under "The no-fabrication guarantee."

**What we're doing about it — health-data privacy.** `DATA_PRIVACY_AND_SAFETY.md` Part 1 documents five
safety mechanisms that already exist in the backend but were invisible in the original pitch because
they live in server-side code: the no-fabrication guarantee (§1.1), a full per-decision audit trail
(§1.2, `decision_audit` table), source-tagging on every AI vs. fallback response (§1.3), a fact-grounding
constraint on the WhatsApp assistant that forbids inventing biomarker values or appointments (§1.4), and
race-safe deterministic booking (§1.5). Part 2 of the same document is deliberately unflattering: it
names five real, current gaps — demo-grade auth, an unauthenticated `/api/readings` endpoint, unverified
encryption-at-rest, no data-retention policy, no signup consent flow — each with a specific remediation
plan and time estimate, several of which are already scoped into `TEAM_AND_ROADMAP.md` Section 2 as
0–6-week items (the `/api/readings` auth header and signup consent flow are both estimated at hours, not
weeks). We chose to publish our own gap list rather than let an evaluator find it first.

All of this — the pipeline diagram, the audit-trail explanation, the no-fabrication guarantee, the
AI/fallback labeling, and the human-in-the-loop handoff — is now surfaced directly on the **public
homepage**, no login required: the Trust & Transparency section (`trust.*` keys in
`frontend/src/i18n/translations.js`, rendered by `TrustTransparencySection.jsx`). This was previously
true only in backend code a demo never showed; it is now something any visitor, including a judge, can
see without credentials.

---

## What's still genuinely unsolved

A judging panel will trust the rest of this document more if it is equally clear about what isn't fixed
yet. Three things remain genuinely open:

1. **No real hardware yet.** The biosensor still returns randomized dummy values. This is Milestone 1
   of `TEAM_AND_ROADMAP.md`, not a solved problem, and no accuracy claim should be read as applying to
   real sensor data until it does.
2. **No real clinical data yet.** The `confirmed_cases` table — the mechanism the similarity-scoring
   engine and the entire clinical validation plan depend on — is empty. It is a working, tested
   mechanism with zero real entries, and the roadmap's first clinical action is simply running it for
   the first time on real, ethics-approved data.
3. **No regulatory approval of any kind.** No submission has been made to any authority. The
   classification analysis in `REGULATORY_AND_CLINICAL_PATHWAY.md` is our own reasoned assessment
   against public frameworks, explicitly flagged where it still needs direct confirmation from Oman
   MOH/DGPA&DC — it is not a claim of approval or even of confirmed classification.

We think a credible, evidence-cited plan for closing these gaps — with the software safety architecture
and regulatory reasoning already done — is a stronger position than pretending they're already closed.
