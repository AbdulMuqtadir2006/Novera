# Novera — Regulatory & Clinical Validation Pathway

**Status:** Pre-clinical research stage. Last updated 2026-08-11.

This document responds directly to the judging panel's feedback on Novera's Technical Product
(1.5/5) and Team & Future Plans (2.5/5) scores: *"There is no plan for clinical trials or the
licensing required to sell a medical device"*; *"provide accuracy evidence against traditional
blood tests on a larger dataset, and involve medical professionals"*; *"define the regulatory
pathway: clinical trials and medical-device licensing."* It sets out, with cited sources, what
regulatory and clinical-validation route Novera actually needs to take, what stage it is honestly
at today, and what can start in the next 3–6 months without waiting for any approval.

---

## 1. Honest current-state summary

Novera today is a **decision-support software pipeline with no real sensor behind it yet**. This
needs to be stated plainly, not softened:

- The ESP32 hardware sketch (`hardware/esp32_sensor/esp32_sensor.ino`) currently generates
  **randomized values** for pH, creatinine, urea, and temperature (`readPH()`, `readCreatinine()`,
  `readUrea()`, `readTemperature()` all call `randomFloat()` against a fixed plausible range) — no
  physical biosensor is wired to real chemistry yet.
- The `confirmed_cases` table — the mechanism that is supposed to hold real, clinician-confirmed
  outcomes and drive the similarity-scoring half of the decision engine — has never been populated
  from an actual patient. It is only ever written to via `screening_cli.py confirm`, and to date
  that command has only been exercised on synthetic/migrated data.
- No accuracy evidence exists against a reference standard (e.g., blood tests) because no real
  paired measurements have been taken.
- No regulatory submission of any kind has been made to any authority.

In short: this is architecture and process validated on synthetic data, not a clinically validated
product. Every claim below is framed against that reality — the goal of this document is to show a
credible, evidence-based route from here to a validated, licensable screening aid, not to claim
readiness that doesn't exist.

---

## 2. Risk classification reasoning

The single most important regulatory fact about Novera's design is this: **it never outputs a
diagnosis.** The scoring engine (`backend/app/core/scoring.py`) computes a reference-range fit and
a similarity score against confirmed prior cases for three candidate categories (KIDNEY, STOMACH,
ORAL); a single constrained LLM call (`backend/app/core/screening_llm.py`) picks one of the three
categories and cites the scores; and the product then routes the person to book a real appointment
with a clinic via WhatsApp. There is no point in the flow where Novera tells a user they have a
disease. It flags a category worth a professional look and hands off to a human.

That hand-off matters for classification under every major framework:

- **IMDRF/GHTF risk model.** The internationally harmonized framework (successor to the old GHTF,
  now maintained by the International Medical Device Regulators Forum) classifies devices A–D by
  risk, with "regulatory controls proportional to risk" as the explicit governing principle
  ([IMDRF/GHTF SG1 — Principles of Medical Device Classification](https://www.imdrf.org/sites/default/files/docs/ghtf/final/sg1/technical-docs/ghtf-sg1-n015-principles-medical-devices-classification-050915.doc)).
  A non-invasive saliva screening aid that does not diagnose and always requires clinician
  confirmation sits at the low end of this scale by design.
- **EU IVDR (Regulation (EU) 2017/746).** The EU's in-vitro diagnostics regulation uses the same
  four-class A–D system, where Class A is self-certifiable low-risk and Class D is reserved for
  transmissible-agent/blood-safety testing
  ([SimplerQMS: EU IVDR Classification](https://simplerqms.com/eu-ivdr-medical-device-classification/);
  [Greenlight Guru: IVDR Classification Explainer](https://www.greenlight.guru/blog/ivdr-classification)).
  Novera is not life-threatening-condition testing and does not stand alone as a basis for
  treatment — it would most plausibly land in the **Class A/B range**, but IVDR classification is a
  formal rule-based exercise (Annex VIII rules) that has not been run for Novera and should not be
  assumed; this needs a proper classification analysis once real sensor specifications exist.
- **US FDA — Clinical Decision Support (CDS) carve-out.** The 21st Century Cures Act (2016) added
  section 520(o)(1)(E) to the FD&C Act, exempting certain CDS software from device regulation if it
  meets four criteria: (1) does not analyze a medical image or a **signal from an in-vitro
  diagnostic device**, (2) displays/analyzes established medical information, (3) supports rather
  than replaces a clinician's judgment, (4) lets the clinician independently review the basis for
  the recommendation
  ([FDA Clinical Decision Support Software guidance, Federal Register, 2022](https://www.federalregister.gov/documents/2022/09/28/2022-20993/clinical-decision-support-software-guidance-for-industry-and-food-and-drug-administration-staff);
  criteria summary via [Frier Levitt](https://www.frierlevitt.com/articles/fda-clinical-decision-support-software-guidance/)).
  **Honest assessment:** Novera would satisfy criteria 2–4 (it presents evidence, doesn't replace
  clinical judgment, and the audit trail lets a clinician see exactly why a category was chosen) but
  is likely to **fail criterion 1**, because a saliva biosensor is functionally an in-vitro
  diagnostic device and its readings are the direct input to the algorithm. That means, under US
  rules, Novera would most likely be regulated as a **device/IVD**, not exempted as non-device CDS —
  we should not claim the CDS exemption applies. It is cited here because it is the clearest
  articulation of *why* the human-in-the-loop, audit-transparent design matters for classification
  even where it doesn't earn a full exemption — the same design features argue for a low risk class
  everywhere else.
- **Oman.** See Section 3 — Oman's own published framework does not yet spell out software/SaMD
  classification specifics, so the honest position is "likely low class, to be confirmed directly
  with Oman MOH."

**Bottom line:** the architecture is deliberately built for a low-risk classification — triage, not
diagnosis, with mandatory human confirmation — and that should be the team's affirmative regulatory
argument, not an afterthought.

---

## 3. Oman's regulatory framework — what is and isn't publicly confirmed

Medical devices in Oman are regulated by the **Ministry of Health's Directorate General of
Pharmaceutical Affairs and Drugs Control (DGPA&DC), Medical Device Control Department**
([RegDesk: Oman Medical Device Regulations](https://www.regdesk.co/regulations-library/oman/)).
Verifiable facts from that source and corroborating coverage:

- Oman uses a four-tier classification (Class A–D) that maps toward the IMDRF-style I–IV scale, with
  classification following the device's country-of-origin jurisdiction (i.e., reliance on a
  reference regulator's classification), subject to Omani reclassification.
- As of **July 2025 (Circular 161/2025)**, Oman opened **mandatory registration for Class C and D
  (high-risk) devices**, moving from a manual to an **electronic portal (live 11 August 2025)**.
  Class A/B (lower-risk) devices are, per that same source, **not currently subject to mandatory
  registration** but do need to be **listed** in the Medical Device Control Department's database
  before import/market placement, with 30-day update obligations and annual confirmation.
- Fees cited: 100 OMR (Class A/B), 200 OMR (Class C/D); target processing window ~60 working days;
  an Omani Authorized Representative is required for the applicant.
- **Not confirmed:** how Oman classifies software-only screening/triage tools specifically (SaMD),
  whether/how the GCC's harmonized pharma/device framework (referred to in industry literature as
  GCC-DR for pharmaceuticals) extends procedurally to Oman's device registration in practice, and
  whether a device built and first deployed in Oman (rather than one with an existing foreign
  classification to "follow") has a defined self-classification procedure. **These should be
  confirmed directly with Oman MOH / DGPA&DC before any submission is planned**, not assumed from
  secondary sources.

Separately, Oman's clinical-research approval structure is real and mapped: the Ministry of
Health's **National Health Research Centre / Centre of Studies and Research** runs the **Research
and Ethical Review & Approval Committee (RERAC)**, constituted by Ministerial Decision in 2011, and
a **Health Studies & Research Approval Committee (HSRAC)**
([MOH Centre of Studies and Research](https://mohcsr.gov.om/hsrac/); [MOH Guidelines for
Responsible Conduct of Clinical Studies and Trials, Aug 2016](https://mohcsr.gov.om/wp-content/uploads/2016/01/Guide_ClinicalStudiesTrials_Aug16.pdf)).
Any human-subjects pilot — even a small concordance study, not a drug trial — should expect to go
through this ethics-approval route, and clinical trials specifically also require sign-off from the
Medicines Regulatory Authority per the same guideline.

---

## 4. International standards Novera should build toward

Regardless of which country receives the eventual submission, any real regulatory dossier will be
assessed against the same core international standards, all of which Oman's MOH is expected to
recognize given its reliance-based classification approach:

| Standard | Scope | Relevance to Novera |
|---|---|---|
| **ISO 13485** | Quality management system for medical device organizations | Governs how Novera's org (not just the code) documents design control, change management, and supplier control |
| **IEC 62304** | Software lifecycle for medical device software | Directly applicable — Novera is software-driven decision support; this standard defines required lifecycle documentation, and classifies software by the harm-if-wrong of its output (Class A/B/C) |
| **ISO 14971** | Risk management for medical devices | Requires a formal risk file — hazard identification (e.g., false negative on a kidney flag), risk controls, residual risk acceptance |
| **IEC 62366-1** | Usability engineering | Relevant to the WhatsApp/app flow — how clearly a "flag" is distinguished from a "diagnosis" in the UI/UX is a usability-safety issue, not just a design preference |

(Sources: [ISO/IEC standards overview](https://attractgroup.com/blog/iso-and-iec-standards-for-samd-breakdown-of-medical-devices/); [IEC 62304 guide](https://intuitionlabs.ai/articles/iec-62304-medical-device-software-guide).)

None of this needs to be *completed* now — but the team should adopt IEC 62304-style documentation
discipline early (design inputs, verification records, a living risk file) because retrofitting it
onto an already-built pipeline is far more expensive than growing it alongside the code.

---

## 5. AI/software-specific considerations

Two US FDA concepts translate directly to Novera's actual architecture, even though Oman submission
is the real target — they're the best-documented thinking on exactly the two design features that
make Novera unusual:

**Predetermined Change Control Plans (PCCP).** FDA's December 2024 final guidance on PCCPs for
AI-enabled devices lets a manufacturer pre-specify *what* will change as a system learns and *how*
it will be validated when it does, instead of requiring a new submission per update
([FDA AI/ML SaMD Action Plan](https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-software-medical-device);
[PCCP guidance summary](https://namsa.com/resources/blog/fdas-regulation-of-ai-ml-samd/)). Novera's
`confirmed_cases` similarity mechanism is exactly this kind of evolving system — as more clinician
confirmations accumulate, the similarity score's behavior shifts. The team should treat this as a
strength to document, not hide: unlike a continuously-retrained model, this is a **bounded,
inspectable** form of learning (a nearest-neighbor lookup against an audited table, not opaque
weight updates), which is a materially easier thing to validate and explain to a regulator than a
black-box retraining loop.

**Human-in-the-loop / CDS framing.** Even where Novera doesn't qualify for the US non-device CDS
exemption (Section 2), the four CDS criteria are a useful internal design checklist: recommendations
should always be explainable, never framed as a diagnosis, and the clinician (or downstream care
provider) should always be able to see the evidence behind a flag. Novera's `decision_audit` table
already satisfies this in spirit — every specialist score, the raw LLM output, and the model used
are stored per case.

---

## 6. Clinical validation study design

The judges' own recommendation — "accuracy evidence against traditional blood tests on a larger
dataset" — maps to a standard diagnostic accuracy study design, reportable under **STARD 2015**
(Standards for Reporting of Diagnostic Accuracy Studies), a 30-item checklist covering study design,
participant flow, the index test, the reference standard, and statistical methods. Sample-size
justification is explicitly item 18 of STARD and is one of the most commonly *missed* items in
published studies — Novera should not repeat that gap.

Proposed design for Novera's first concordance study:

- **Index test:** Novera saliva readings (pH, urea, creatinine, temperature) → category flag.
- **Reference standard:** paired venous blood test panel measuring the clinically standard
  correlates — e.g., serum creatinine/eGFR and BUN for the kidney pathway. The exact panel needs to
  be defined jointly with a partner clinician/lab (see Section 8) — this document does not invent
  specific cutoffs.
- **Population:** a real but modest pilot cohort (order of 50–100 participants, consistent with an
  early feasibility/concordance study rather than a pivotal trial) recruited through a partner
  clinic, with informed consent and RERAC/HSRAC ethics approval per Section 3.
- **Metrics:** sensitivity, specificity, PPV, NPV, and concordance (e.g., Cohen's kappa) between
  Novera's flag and the reference-standard-based clinical assessment, per organ category.
- **Data pipeline:** every enrolled participant's *real* outcome, once adjudicated by the partner
  clinician, is entered through the **existing** `screening_cli.py confirm --case-id N... --organ
  ... --confirmed-by Dr.X` command. This is not new infrastructure — it is the literal mechanism
  the codebase already has for exactly this purpose, simply never yet run against real patients.
- **Oversight:** a named clinical lead (physician or lab director) reviews and adjudicates the
  reference-standard outcome for every case before it is entered as a "confirmed" ground truth —
  this directly answers the judges' "involve medical professionals" comment.

---

## 7. Phased pathway

| Phase | Focus | Exit criteria |
|---|---|---|
| **Phase 0 (now)** | Software pipeline validated on synthetic/dummy sensor data only | Scoring + LLM decision + audit trail work end-to-end (already true) |
| **Phase 1** | Real sensor integration + analytical/bench validation | Device readings for pH/creatinine/urea/temperature verified against known reference solutions/standards, not just plausible ranges |
| **Phase 2** | Clinical concordance study (Section 6) | Sensitivity/specificity vs. blood-test gold standard computed on a real, ethics-approved pilot cohort; `confirmed_cases` populated from real adjudicated outcomes |
| **Phase 3** | Formal regulatory submission | ISO 13485 QMS in place, IEC 62304 software file complete, ISO 14971 risk file complete, submission through Oman MOH/DGPA&DC (classification confirmed directly with MOH per Section 3) |

Each phase's exit criteria is a gate — Phase 3 should not start until Phase 2 produces real
sensitivity/specificity numbers, and Phase 2 should not start until Phase 1 shows the sensor itself
is trustworthy independent of the software.

---

## 8. What's already built that helps this pathway

The judges' "no plan" comment is fair for documentation, but it understates what already exists in
the code as *infrastructure* for exactly this pathway:

- **Full decision audit trail** (`decision_audit` table) — every case's specialist scores, raw LLM
  output, and model identity are stored, which is the raw material for a regulator's traceability
  requirement and for the concordance study's data analysis.
- **Fail-safe, never-fabricate design** — if the LLM call fails for any reason, the case is released
  back to `NEW` status with nothing saved (`screening_llm.process_case_stream`); Novera never
  invents a result. This is a genuinely strong safety property to lead with in any submission.
- **A working confirmed-case data pipeline** — the `confirm` CLI and `confirmed_cases` table are not
  a gap to build; they are the literal mechanism Section 6's study would use to build a validated
  dataset over time. It is empty, not missing.
- **A category-flag-then-human-handoff product flow** — the WhatsApp appointment-booking routing is
  the structural reason the risk-classification argument in Section 2 is credible, not aspirational.

---

## 9. Concrete near-term action items (next 3–6 months)

These require no regulatory approval and can start now:

1. **Identify 1–2 partner clinicians or a hospital lab** (e.g., through Oman MOH's National Health
   Research Centre channels) willing to advise on and host a small pilot concordance study.
2. **Define the exact reference blood-test panel** per organ category (kidney, oral, stomach/
   digestive) jointly with that clinical partner — this document deliberately does not invent
   specific thresholds.
3. **Confirm Oman's SaMD/software classification treatment directly with DGPA&DC**, since it is not
   resolved in public sources (Section 3).
4. **Begin Phase 1 bench validation planning** — identify certified reference solutions for pH,
   creatinine, and urea to test the real sensor against once hardware integration starts.
5. **Start using `screening_cli.py confirm` on any real pilot data** as soon as the first ethics-
   approved participants are enrolled, so the `confirmed_cases` similarity mechanism starts being
   built on real, not synthetic, outcomes.
6. **Draft the ISO 14971 risk file skeleton** now (hazards, e.g., false-negative kidney flag; current
   controls, e.g., mandatory clinician follow-up) — cheap to start early, expensive to retrofit.
7. **Submit the pilot study protocol to Oman MOH's RERAC/HSRAC** for ethics review once the partner
   clinician and reference panel are defined.

---

## Sources

- IMDRF/GHTF SG1 — [Principles of Medical Device Classification](https://www.imdrf.org/sites/default/files/docs/ghtf/final/sg1/technical-docs/ghtf-sg1-n015-principles-medical-devices-classification-050915.doc)
- RegDesk — [Oman Medical Device Regulations, Classifications & Approvals](https://www.regdesk.co/regulations-library/oman/)
- Oman MOH Centre of Studies and Research — [HSRAC](https://mohcsr.gov.om/hsrac/), [Guidelines for Responsible Conduct of Clinical Studies and Trials, Aug 2016 (PDF)](https://mohcsr.gov.om/wp-content/uploads/2016/01/Guide_ClinicalStudiesTrials_Aug16.pdf)
- EU IVDR classification — [SimplerQMS](https://simplerqms.com/eu-ivdr-medical-device-classification/), [Greenlight Guru](https://www.greenlight.guru/blog/ivdr-classification)
- FDA — [Clinical Decision Support Software guidance, Federal Register 2022](https://www.federalregister.gov/documents/2022/09/28/2022-20993/clinical-decision-support-software-guidance-for-industry-and-food-and-drug-administration-staff); criteria summary via [Frier Levitt](https://www.frierlevitt.com/articles/fda-clinical-decision-support-software-guidance/)
- FDA — [Artificial Intelligence and Machine Learning in Software as a Medical Device](https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-software-medical-device); PCCP summary via [NAMSA](https://namsa.com/resources/blog/fdas-regulation-of-ai-ml-samd/)
- ISO/IEC standards for SaMD — [Attract Group overview](https://attractgroup.com/blog/iso-and-iec-standards-for-samd-breakdown-of-medical-devices/), [IEC 62304 guide](https://intuitionlabs.ai/articles/iec-62304-medical-device-software-guide)
- STARD 2015 — [STARD 2015 guidelines: explanation and elaboration, PubMed](https://pubmed.ncbi.nlm.nih.gov/28137831/)

## Explicitly unverified — confirm with Oman MOH / DGPA&DC directly

- How Oman classifies **software-only** screening/decision-support tools (SaMD) specifically —
  public sources describe hardware device classification only.
- Whether/how any GCC-wide harmonized device framework procedurally applies to Oman's own
  registration process (as distinct from Oman's own Circular 161/2025 process).
- The self-classification procedure for a device with **no existing foreign classification to
  follow** (Oman's published approach references classifying "according to the country of origin
  jurisdiction," which presumes an existing classification elsewhere).
- Current registration/listing fees and timelines beyond what is cited above, which the source
  itself flags as not necessarily current.
