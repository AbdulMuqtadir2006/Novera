# Novera — Team, Roles & Roadmap

**Status:** Living planning document. Last updated 2026-08-11.

This document responds to the judging panel's Team & Future Plans score (2.5/5) and the recurring
theme across other criteria that Novera lacked a concrete, sequenced plan — as opposed to aspirational
language — for getting from where it is today to a validated product. It is deliberately specific:
every milestone below names the file, command, or document it depends on, so it can be checked against
the actual repository rather than taken on faith.

It should be read alongside two companion documents produced in this same effort:
[`REGULATORY_AND_CLINICAL_PATHWAY.md`](./REGULATORY_AND_CLINICAL_PATHWAY.md) (the clinical/regulatory
route) and [`DATA_PRIVACY_AND_SAFETY.md`](./DATA_PRIVACY_AND_SAFETY.md) (safety architecture and honest
security gaps). This document is the execution plan that ties both of those to dates and effort
estimates.

---

## 1. Honest starting point

Two things are true at once, and the roadmap only makes sense if both are held together:

- The **screening decision software** — reference-range scoring, similarity scoring against
  clinician-confirmed prior cases, a single constrained LLM decision call, and a full audit trail — is
  real, already built, and already working end-to-end (`backend/app/core/scoring.py`,
  `backend/app/core/screening_llm.py`, `db/schema.sql`). It currently has **zero real confirmed
  cases** because the `confirm` mechanism has only ever been run on synthetic/migrated data.
- The **saliva biosensor hardware does not exist yet.** The ESP32 firmware
  (`hardware/esp32_sensor/esp32_sensor.ino`) is explicitly labelled "DUMMY MODE" in its own header
  comment (lines 11–27) and its four read functions —`readPH()`, `readCreatinine()`, `readUrea()`,
  `readTemperature()` (lines 79–82) — each call a `randomFloat(lo, hi)` helper returning a plausible
  number inside a fixed reference band, not a real chemical measurement. This is the single biggest
  gap the judges identified ("the hardware is not built... every accuracy claim is hypothetical") and
  the roadmap below treats it as exactly that: the first, unstarted milestone, not a solved problem.

Real sensor integration is therefore Milestone 1, not an afterthought — everything downstream
(clinical concordance data, regulatory submission, accuracy claims) is gated on it.

---

## 2. Immediate next steps (0–6 weeks) — no funding or regulatory approval required

These can start now, in parallel, using only engineering time and the existing codebase.

| Item | What it actually involves | Why it's low-cost |
|---|---|---|
| **Real sensor integration (software side)** | Replace the body of `readPH()`, `readCreatinine()`, `readUrea()`, `readTemperature()` in `esp32_sensor.ino` with real ADC/sensor-library reads once physical sensor hardware is sourced | The firmware's own header comment (lines 11–27) documents this as the intended swap point — "replace this function with the real sensor read (analogRead(PIN), a sensor library call, ...)". The HTTP payload shape, backend ingestion (`POST /api/readings`), scoring engine, and frontend are all sensor-agnostic and require **zero changes** — this is a hardware/firmware task, not a full-stack one |
| **Source physical sensor components** | pH probe + ADC, creatinine/urea biosensor strips or equivalent electrochemical sensing, calibrated temperature probe | Procurement + a hardware/embedded engineer's time; the interface contract (4 floats over HTTP) is already fixed by the working software, which narrows the sourcing problem to "find sensors that report these 4 values," not "redesign the pipeline" |
| **Start running `screening_cli.py confirm` on any real readings** | As soon as even one real (non-dummy) reading exists — from an early bench-tested sensor or a manually-entered pilot reading — a clinician or team member can run `confirm --case-id N --organ ... --confirmed-by Dr.X` against it | This is the **existing** mechanism (`REGULATORY_AND_CLINICAL_PATHWAY.md`, Section 8) — no new code, just the first real use of a command that has so far only touched synthetic data. Each confirmed case incrementally improves the similarity-scoring half of the decision engine |
| **Harden `POST /api/readings` with a device auth header** | Add a static `X-Device-Key` header check against a `DEVICE_API_KEY` environment variable, rejecting unauthenticated posts with 401 | Per `DATA_PRIVACY_AND_SAFETY.md` §2.2, this is the document's own top-priority fix and is scoped at **~1 hour** of backend work plus flashing the key onto device firmware — small, bounded, and already fully specified |
| **Add signup consent flow** | Required consent checkbox at signup + a `consent_accepted_at` column on `users` | Per `DATA_PRIVACY_AND_SAFETY.md` §2.5, scoped at **~2–4 hours** of backend work; the larger cost is writing the actual privacy-notice text, a content task that can run in parallel with the engineering |
| **Session hardening (password length, logout-all-sessions)** | Raise minimum password length to 10–12 chars with a common-password check; add a "log out of all sessions" endpoint | Per `DATA_PRIVACY_AND_SAFETY.md` §2.1, estimated at **~1–2 hours** and **~1 hour** respectively — small, immediately actionable |
| **Confirm Railway's at-rest encryption posture** | Get a direct answer from Railway support/docs and record it in `DATA_PRIVACY_AND_SAFETY.md` §2.3 | Currently genuinely unverified from code alone — this is a **~30 minute** question to the platform, not an engineering task |
| **Draft ISO 14971 risk-file skeleton** | Hazards (e.g., false-negative kidney flag), current controls (e.g., mandatory clinician follow-up) | Per `REGULATORY_AND_CLINICAL_PATHWAY.md` §9 item 6 — cheap to start now, expensive to retrofit onto an already-built pipeline later |

None of the above requires a partner clinic, ethics approval, or a regulator. They are the concrete,
scoped items a small team can execute in the next 4–6 weeks with existing skills and the codebase as
it stands today.

---

## 3. 3–6 month milestones — requires a clinical partner

These map directly onto Phase 1 and the start of Phase 2 in `REGULATORY_AND_CLINICAL_PATHWAY.md` §7.

1. **Bench/analytical validation of the real sensor (Phase 1).** Test the physical pH, creatinine,
   and urea sensors against certified reference solutions — independent of the software — before any
   patient contact. Exit criterion: device readings verified against known standards, not just
   "plausible ranges."
2. **Identify 1–2 partner clinicians or a hospital lab.** Per the regulatory pathway's own recommended
   channel (Oman MOH's National Health Research Centre), to advise on and host a small pilot.
3. **Define the reference blood-test panel per organ category** (kidney, oral, stomach/digestive)
   jointly with that clinical partner — deliberately not invented unilaterally by this team, per
   `REGULATORY_AND_CLINICAL_PATHWAY.md` §6.
4. **Submit the pilot protocol to Oman MOH's RERAC/HSRAC** for ethics review once the partner and
   panel are defined.
5. **Run the pilot clinical concordance study (Phase 2 start).** A modest cohort (order of 50–100
   participants, per the regulatory doc's STARD-aligned design) with informed consent, comparing
   Novera's flag against the blood-test reference standard. Every adjudicated outcome is entered
   through the **existing** `confirm` CLI, which is the literal mechanism this study populates.
6. **Report accuracy against traditional blood tests.** Sensitivity, specificity, PPV, NPV, and
   concordance (Cohen's kappa) per organ category — the direct, evidence-based answer to the judges'
   "provide accuracy evidence... on a larger dataset" recommendation, produced from real data rather
   than asserted.

Exit criterion for this phase (per the regulatory doc's phase gates): Phase 3 does not start until
this phase produces real sensitivity/specificity numbers.

---

## 4. 6–18 month milestones — regulatory submission and scaling

1. **Formal regulatory submission track (Phase 3/4).** ISO 13485 QMS in place, IEC 62304 software
   file complete, ISO 14971 risk file complete (built on the skeleton started in Section 2), and
   submission through Oman MOH/DGPA&DC once the SaMD classification question is confirmed directly
   with the ministry (`REGULATORY_AND_CLINICAL_PATHWAY.md` §3, §9 item 3).
2. **Scale the `confirmed_cases` dataset.** Expand beyond the pilot cohort as more clinics and
   clinicians adopt the confirm workflow, strengthening the similarity-scoring half of the decision
   engine with real, adjudicated outcomes rather than synthetic data.
3. **Google Play Store publishing (Android).** The Android app currently builds automatically via CI
   as a **debug APK only** — per the project's own `AI_CONTEXT.md` ("Android Play Store publishing —
   not done; app is a sideloaded debug APK only"), publishing requires a one-time $25 developer
   registration fee, a signed release build (as opposed to the current CI debug build), and the Play
   Store review process. This is a scoped, well-understood distribution task, not an open technical
   question.
4. **iOS native app — if justified.** Evaluate based on real user/clinic demand once the Android
   release is live; no iOS work exists yet and none should be assumed before the Android release
   proves out distribution and usage patterns.
5. **PCCP documentation.** Formalize the "Predetermined Change Control Plan" framing already discussed
   in `REGULATORY_AND_CLINICAL_PATHWAY.md` §5 for how the `confirmed_cases` similarity mechanism is
   allowed to evolve post-approval without triggering a full resubmission each time.

---

## 5. Team & roles needed

This section is intentionally a statement of **required expertise**, not a claim about who is already
hired or contractually committed. No specific individuals are named because none are committed yet —
overstating this would not survive the same scrutiny this document is trying to satisfy.

| Role | Why the roadmap needs it | When |
|---|---|---|
| **Clinician / medical advisor** | Defines the reference blood-test panel, adjudicates real outcomes entered via the `confirm` CLI, provides the "involve medical professionals" credibility the judges asked for directly | Needed starting Section 3 (3–6 month phase); ideally identified during Section 2 |
| **Hardware / embedded engineer** | Owns real sensor sourcing, calibration, and the firmware swap described in Section 2 — the single highest-priority technical gap | Needed immediately (Section 2) |
| **Regulatory / QA support** | Owns the ISO 13485 / IEC 62304 / ISO 14971 documentation discipline and the Oman MOH/DGPA&DC submission process | Needed from Section 2 (starting the risk-file skeleton) through Section 4 |
| **Backend engineer** (existing capability) | Implements the near-term security hardening items (Section 2) and any schema work needed for retention/consent (`DATA_PRIVACY_AND_SAFETY.md` §2.4) | Ongoing |
| **Data protection / legal review** | Needed before Novera handles real patient data at scale — specifically the retention-policy decision and the encryption-at-rest question are flagged in `DATA_PRIVACY_AND_SAFETY.md` as product/legal calls, not unilateral engineering ones | Needed before Section 3 pilot begins collecting real patient data |

The current team's demonstrated capability — a working, audited decision-support pipeline with a real
safety architecture (see `DATA_PRIVACY_AND_SAFETY.md` Part 1) built before any hardware or clinical
partner existed — is itself evidence that the software risk is well in hand. What the roadmap above
adds is the hardware, clinical, and regulatory expertise the team does not yet have in-house, sequenced
so that each phase's output is what the next phase's gate requires.

---

## 6. Summary timeline

```
Weeks 0-6      Real sensor integration (firmware) | confirm CLI on first real data |
               API auth hardening | signup consent | risk-file skeleton
Months 3-6     Bench validation | clinical partner + ethics approval | pilot concordance study |
               accuracy report vs. blood tests
Months 6-18    ISO 13485/62304/14971 complete | Oman MOH submission | confirmed_cases scaling |
               Play Store release | iOS evaluation
```

Each phase is gated on the previous one producing real evidence, not a target date — per
`REGULATORY_AND_CLINICAL_PATHWAY.md` §7, Phase 3 does not start until Phase 2 produces real
sensitivity/specificity numbers, and Phase 2 does not start until Phase 1 shows the sensor itself is
trustworthy independent of the software.
