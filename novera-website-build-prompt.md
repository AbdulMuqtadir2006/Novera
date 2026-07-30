# Novera — Website Build Brief for Claude Code

You are building the marketing website and product app for **Novera**, an agentic AI-driven saliva biosensor platform for non-invasive health screening. One saliva sample goes into a sensor; a coordinated system of AI agents turns the biomarker signal into a screening summary across four health areas. Build everything below fully — don't stop at a scaffold. Every page should be genuinely interactive and demoable on mock data, not lorem-ipsum placeholders.

**Tip:** paste this whole file as your first message to Claude Code, or save it as `CLAUDE.md` in the project root so it stays in context for the rest of the build.

---

## 1. Tech Stack

- **React 18** + **Vite**
- **Tailwind CSS** — all styling; no component library fighting Tailwind
- **React Router** (latest) — the 6 top-level routes
- **Framer Motion** (may now resolve as the `motion` package — same author, install whichever is current) for transitions, staggered reveals, hover/press states
- **GSAP + ScrollTrigger** for the scroll-scrubbed hero and any pinned/scrubbed storytelling — fully free to use, no paid tier
- **Recharts** for the Dashboard charts
- **lucide-react** for icons
- **jsPDF** + **jspdf-autotable** for client-side PDF report generation
- **Web Speech API** (`window.speechSynthesis`) for the Voice tab — ships working with zero API keys
- A small mock **data layer** standing in for the real SQL-backed API — see §10 before wiring the Dashboard

## 2. Design System

**Why this palette:** saliva biosensing lives in a lab-precision, signal-reading world, not a generic "wellness app teal." A dark base on the homepage lets the frame sequence and its glow read like an instrument coming alive — a light background would wash out a subtle product reveal. The light-blue/white split on the app pages answers the "light blue" brief directly and reads as a calmer, clinical space once someone's looking at their own numbers. The amber accent keeps the system from going cold — it's the one warm color against all the blue and teal.

| Token | Hex | Use |
|---|---|---|
| `ink` | `#0B1120` | Homepage base — dark canvas around the frame sequence |
| `signal` | `#3FE1D6` | Primary accent (teal/cyan glow) — chart lines, active states, agent pulses, hero glow |
| `vital` | `#F2A93E` | Secondary accent (warm amber) — CTAs, highlights |
| `mist` | `#EAF3FB` | Light-blue background for every non-homepage page |
| `paper` | `#F8FBFE` | Card/surface tone on light pages, incl. the subpage navbar |
| `depth` | `#123A5C` | Heading/body text on light pages |

Status colors (Dashboard only): `status-good` `#3DDC97` · `status-watch` `#F2A93E` · `status-attention` `#FF5D5D`

**Typography** — three roles, register all of them in `tailwind.config.js` (`theme.extend.fontFamily`) alongside the colors above (`theme.extend.colors`) rather than hardcoding hex/fonts inline anywhere:
- **Display — Bricolage Grotesque** (Google Fonts): headlines, hero text, section headings. Has enough personality to carry the hero without extra decoration.
- **Body — Hanken Grotesk** (Google Fonts): paragraphs, nav, UI copy. Shares grotesk DNA with the display face so the pairing feels considered.
- **Data/mono — IBM Plex Mono** (Google Fonts): biomarker numbers, timestamps, agent status labels. Gives readings an instrument-panel precision.

**Homepage layout concept:**
```
┌───────────────────────────────────┐
│ NAV (transparent → glass on scroll)│
├───────────────────────────────────┤
│                                     │
│   240-FRAME PRODUCT REVEAL (pinned)│
│      headline + scroll captions    │
│                                     │
├───────────────────────────────────┤
│  WHAT NOVERA IS                    │
├───────────────────────────────────┤
│  AGENTS AT WORK                    │
├───────────────────────────────────┤
│  HEALTH AREAS (4-card grid)        │
├───────────────────────────────────┤
│  HOW IT WORKS                      │
├───────────────────────────────────┤
│  RESEARCH NOTE  →  CTA  →  FOOTER  │
└───────────────────────────────────┘
```

**Signature move:** the frame-scrub hero, staged with scroll-synced captions (§4.1). Let that be the one genuinely bold thing on the page. Keep Agents / Health Areas / How It Works precise and quiet by comparison so the hero doesn't have to compete for attention — that contrast is what makes it land. Spend the "crazy animation" budget there; everywhere else, pull from the toolbox in §11 only where it earns its place.

## 3. Global Layout

**Navbar** — 6 links: Home, Dashboard, Reports, Voice, Self Care, and a 6th (call it "More" for now, easy to rename later).
- On Home: transparent over the hero, crossfades to a translucent `ink` glass bar (backdrop-blur) once scrolled past it.
- On every other page: solid `paper`, `depth` text, sitting above the `mist` page body.
- Active route: an animated pill/underline that slides between items (Framer Motion `layoutId` is built for exactly this).
- Mobile: hamburger → full-screen overlay, links reveal with a staggered fade/slide.

**Footer** — wordmark + tagline, three link columns (Product / Company / Legal), social icons, the research disclaimer line from §4.6, copyright.

**Page shell** — a `<PageShell>` wrapper every non-home route uses: applies `mist` background, top padding for the fixed navbar, consistent max-width container. Keeps every subpage visually consistent without repeating layout code per page.

## 4. Homepage (`/`)

### 4.1 Hero — the 240-frame scroll sequence

This is the centerpiece — get it right before polishing anything else.

**Assets:** you already have the 240 rendered frames. Export as `frame_0001.webp` … `frame_0240.webp`, zero-padded to 4 digits, into `public/frames/`. Keep each frame reasonably sized (~1600×900, compressed WebP) — 240 uncompressed PNGs will make the page unusable. Downscale/recompress before dropping them in.

**Mechanism:** pin the hero for several viewport-heights of scroll and scrub a `<canvas>` through the 240 frames as the user scrolls — the same technique Apple uses on its product pages. Reference implementation (a skeleton — flesh out cover-fit image drawing and the fallback notes below before calling it done):

```jsx
// src/hooks/useScrollFrameSequence.js
import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const FRAME_COUNT = 240;
const getFramePath = (i) =>
  `/frames/frame_${String(i + 1).padStart(4, "0")}.webp`;

export function useScrollFrameSequence(canvasRef, sectionRef) {
  const imagesRef = useRef([]);
  const [ready, setReady] = useState(false);
  const [progress, setProgress] = useState(0); // 0..1 — drives the caption labels below

  useEffect(() => {
    let loaded = 0;
    imagesRef.current = Array.from({ length: FRAME_COUNT }, (_, i) => {
      const img = new Image();
      img.src = getFramePath(i);
      img.onload = () => { loaded += 1; if (loaded === FRAME_COUNT) setReady(true); };
      return img;
    });
  }, []);

  useEffect(() => {
    if (!ready || !canvasRef.current || !sectionRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;

    const draw = (index) => {
      const img = imagesRef.current[index];
      if (!img?.complete) return;
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      // TODO: cover-fit math (match canvas aspect to image aspect) instead of a plain stretch
      ctx.drawImage(img, 0, 0, window.innerWidth, window.innerHeight);
    };

    const resize = () => {
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw(Math.floor(progress * (FRAME_COUNT - 1)));
    };
    resize();
    window.addEventListener("resize", resize);

    const trigger = ScrollTrigger.create({
      trigger: sectionRef.current,
      start: "top top",
      end: "+=400%",
      pin: true,
      scrub: 0.4,
      onUpdate: (self) => {
        setProgress(self.progress);
        draw(Math.floor(self.progress * (FRAME_COUNT - 1)));
      },
    });

    return () => { trigger.kill(); window.removeEventListener("resize", resize); };
  }, [ready]);

  return { ready, progress };
}
```

**Composition — read this carefully:** the product is forming in the center of the screen as the user scrolls, so every other element in this section has to be placed *around* it, never on top of it.
- Keep a clear channel of negative space where the product silhouette forms — don't center a text block over it.
- Headline + subhead sit above the fold (before the pin starts) or fixed to one side, wherever it doesn't overlap the forming object — test against the real frames and pick whichever reads cleaner.
- Add small caption labels that fade in/out at scroll-progress checkpoints (the hook exposes `progress` from 0–1 for exactly this) to narrate the formation — roughly 25%: *"Capturing signal"*, 50%: *"Cross-referencing biomarkers"*, 75%: *"Modeling your screening"*, 100%: *"Your result, assembled."* Place these beside the product, never over it.
- A small scroll cue — *"Scroll to watch it come together ↓"* — at the very start, fading out as soon as scroll begins.

**Fallback & performance:**
- Respect `prefers-reduced-motion`: skip the scrub entirely, show the final assembled frame as a static image.
- Below the `md` breakpoint, consider a lighter path — a reduced frame subset (every 2nd frame) or a single autoplay-muted looping video export of the same animation. Full 240-frame preload on mobile data is a real risk.
- Show a minimal branded loading state while frames preload — a thin progress bar or the `signal` color pulsing is enough.

**Copy** (draft — adjust freely):
- Eyebrow: `NOVERA RESEARCH PLATFORM`
- Headline: **"One sample. A full picture."**
- Subhead: *"Saliva carries more signal than we give it credit for. Novera's sensors capture it, and a system of AI agents cleans, cross-references, and explains it — turning a short sample into a screening summary you can actually read."*

### 4.2 What Novera Is

- Eyebrow: `THE IDEA`
- Heading: **"Health screening shouldn't need a needle."**
- Body: *"Traditional screening means blood draws, lab queues, and days of waiting. Novera reads biomarker signals directly from saliva instead. A sample goes into the sensor; a system of AI agents takes it from there — checking the signal against research models for kidney function, hydration, oral health, and digestive health, and returning a screening summary in minutes."*
- Smaller line beneath: *"This is a research platform, not a diagnostic device — built to explore what saliva can tell us, faster than conventional screening allows."*

### 4.3 Agents at Work

- Eyebrow: `HOW IT THINKS`
- Heading: **"A pipeline of agents, working while you wait."**
- Intro line: *"Every reading passes through a coordinated system of AI agents, each responsible for a different part of turning a raw signal into something you can understand."*
- Four agent cards, revealed in sequence as the section scrolls into view (stagger the reveal; animate a connecting line drawing between them — SVG `stroke-dashoffset` is the clean way to do this). *These four are a suggested structure that mirrors the app's Dashboard / Voice / Self Care / Reports tabs — rename or restructure to match your actual agent architecture if it differs:*
  1. **Capture Agent** — "Reads the raw biomarker signal the moment your sample hits the sensor."
  2. **Analysis Agent** — "Cross-references pH, creatinine, urea, and temperature against Novera's four screening models."
  3. **Insight Agent** — "Turns the analysis into plain language and flags anything worth a closer look."
  4. **Guidance Agent** — "Builds your next steps — self-care suggestions, your spoken summary, your report."
- Give each card a soft pulsing ring in `signal` to sell the idea that these are actively working, not static icons.

### 4.4 Health Areas

| Area | Copy (as given — use exactly) | Suggested icon |
|---|---|---|
| Kidney Health | Monitor biomarkers that may indicate kidney function changes over time. | `Filter` (kidneys filter — closest conceptual match in lucide-react) |
| Hydration | Track hydration balance through saliva-based hydration index. | `Droplets` |
| Oral Health | Detect early oral protein indicators for proactive dental wellness. | `Smile` (swap for a dedicated tooth icon if your installed lucide-react version has one) |
| Digestive Health | Observe salivary markers related to digestive system function. | `Activity` |

Heading: `Health Areas` · Subhead: *"Our research platform currently explores screening signals in four health areas."* (both exactly as given).

> Your message cut off mid-sentence on the Digestive Health line ("…digestive system function…"). I closed it at "function." — swap in your real copy before this ships.

Card motion: staggered fade/slide-up on scroll into view, subtle tilt + glow border on hover — nothing louder than that. This section should read as calm and credible next to the hero.

### 4.5 How It Works

- Eyebrow: `THE PROCESS` · Heading: **"From sample to summary"**
1. **Sample** — Provide a saliva sample. No needles, under a minute.
2. **Capture** — Novera's sensor reads the biomarker signal instantly.
3. **Analyze** — AI agents cross-reference it against the four screening models.
4. **Understand** — View your dashboard, hear it explained, or download your report.

### 4.6 Research Note

One quiet, footer-adjacent line, not alarmist: *"Novera is a research-stage screening platform, built to explore what saliva biomarkers can tell us — not to diagnose, treat, or replace care from a medical professional."*

### 4.7 CTA + Footer

Heading: **"See what a single sample can tell you."** Button routes to `/dashboard`. Footer per §3.

## 5. Dashboard (`/dashboard`)

- Background: `mist`
- Header: "Your Latest Reading" + formatted timestamp of the most recent entry
- Four metric cards — **pH, Creatinine, Urea, Temperature** — big value set in `IBM Plex Mono`, unit, a color-coded status badge (good/watch/attention), small inline sparkline
- Below: a full trend chart per metric (Recharts `AreaChart` or `LineChart`) with a time-range toggle (7 days / 30 days / all), plotted against its reference range
- Optional: one combined "screening summary" ring/gauge rolling the four health areas into a single glanceable state
- Every number on this page comes from the mock data layer in §10 — nothing hardcoded in JSX

## 6. Reports (`/reports`)

- Background: `mist`
- A preview panel showing what the report contains, plus a **Download PDF** button
- PDF (client-side, jsPDF + jspdf-autotable) includes: Novera header/wordmark, reading timestamp, a table of the four biomarkers with values + status, a short plain-language summary per health area, and the research line from §4.6
- Nice-to-have: a brief success state after download, not a silent file drop

## 7. Voice (`/voice`)

- Background: `mist`
- Centerpiece: an animated voice-agent orb/waveform that pulses while speaking, idle otherwise — sync its state to the Speech Synthesis `start`/`end`/`boundary` events rather than faking it on a timer
- Controls: Play / Pause / Replay, with the full transcript shown below the orb
- Script is composed from the latest reading (same data source as the Dashboard) — write it as a **screening summary**, not a clinical diagnosis, to stay consistent with the research-stage positioning on the homepage
- Ship with the native Web Speech API first — works with zero setup. Leave a clear seam to swap in a premium TTS API (e.g. ElevenLabs) later if the built-in voice isn't enough

## 8. Self Care (`/self-care`)

- Background: `mist`
- Pull the latest reading's health-area statuses and turn each into a short, practical recommendation (a "watch" on Hydration surfaces a hydration-focused tip, a "watch" on Kidney surfaces a kidney-friendly note, etc.) — a simple rule-based mapping is enough for v1, no ML needed
- Reuse the four health-area icons from §4.4 so this page visually rhymes with the homepage
- Layout: one "Today's Focus" hero card + a grid of the four area-specific recommendation cards

## 9. Sixth Tab (`/more` — placeholder)

- Background: `mist`
- A deliberate "coming soon" state, not a blank/broken-looking page: centered icon, one heading, one short line, nav still fully functional. Rename the route once you've decided what this becomes.

## 10. Data Layer — read before wiring the Dashboard

A browser can't connect to a raw SQL database directly — there's no safe way to ship database credentials to client-side JS. Once you're ready to go live you'll need one of:
1. A small backend (Node/Express or similar) that queries the SQL database and exposes a REST endpoint the frontend calls.
2. A backend-as-a-service like Supabase (Postgres underneath) with a JS client that's safe to call from the browser via row-level security.

Don't block the build on that decision. Build against a mock layer so every page above is fully functional right now, with a one-line swap later:

```js
// src/lib/api.js — swap the body of these two functions for a real fetch()/Supabase
// call once the backend exists. Nothing else in the app should need to change.
import { mockReadings } from "../data/mockReadings";

export async function getLatestReading() {
  return mockReadings.at(-1);
}

export async function getReadingHistory(days = 30) {
  return mockReadings.slice(-days);
}
```

```js
// src/data/mockReadings.js — illustrative shape; adjust ranges to your real sensor calibration
export const mockReadings = [
  {
    timestamp: "2026-07-25T09:14:00Z",
    metrics: {
      ph:          { value: 6.8, unit: "",      range: [6.2, 7.6], status: "good" },
      creatinine:  { value: 1.1, unit: "mg/dL",  range: [0.6, 1.3], status: "good" },
      urea:        { value: 34,  unit: "mg/dL",  range: [7, 20],    status: "watch" },
      temperature: { value: 36.9, unit: "°C",    range: [36.1, 37.2], status: "good" },
    },
    healthAreas: { kidney: "good", hydration: "watch", oral: "good", digestive: "good" },
  },
  // ...generate ~30 days of plausible entries so the trend charts have something to plot
];
```

## 11. Animation Toolbox (use with restraint)

The hero is the one big swing — that's where the "crazy" budget goes. Everywhere else, pull from this list only where it earns its place, not on every element:
- Kinetic headline reveal — split text into words/characters, stagger in on load or scroll
- Number counters that animate up when scrolled into view
- Magnetic pull on primary CTA buttons (subtle cursor-follow within a small radius)
- Card hover: soft 3D tilt + glow border, not a full flip
- SVG line-draw connectors for the agents pipeline
- Route transitions via Framer Motion `AnimatePresence` (fade/slide, ~200–300ms — nothing longer)
- Status badges with a soft pulse ring to sell "live" data on the Dashboard

## 12. Suggested Folder Structure

```
src/
  main.jsx
  App.jsx
  pages/
    Home.jsx  Dashboard.jsx  Reports.jsx  Voice.jsx  SelfCare.jsx  ComingSoon.jsx
  components/
    layout/    Navbar, Footer, PageShell
    home/      FrameScrubHero, ExplanationSection, AgentsSection,
               HealthAreasSection, HowItWorksSection, CtaSection
    dashboard/ ReadingCard, TrendChart, StatusBadge
    reports/   ReportPreview, generateReportPdf.js
    voice/     VoiceOrb, TranscriptPanel
    selfcare/  DietPlanCard
  data/        mockReadings.js, healthAreas.js, agents.js
  hooks/       useScrollFrameSequence.js, useLatestReading.js
  lib/         api.js
  styles/      index.css  (Tailwind directives + the tokens from §2)
public/
  frames/      frame_0001.webp ... frame_0240.webp
```

## 13. Definition of Done

- All 6 routes built and navigable — none a bare scaffold
- Frame-scrub hero runs smoothly, has a `prefers-reduced-motion` fallback, doesn't choke the mobile experience
- Every "live" number on Dashboard/Reports/Voice/Self Care comes from the mock data layer
- Nav, buttons, and links are all keyboard-navigable with visible focus states
- Color contrast holds up on the light `mist`/`paper` pages, not just the dark hero
- Routes are code-split (`React.lazy` + `Suspense`) so the homepage isn't paying for the other pages' bundle weight
- No console errors or warnings, at any breakpoint from mobile to desktop

## 14. If Something's Unclear

Ask before making a structural call that isn't covered above (exact SQL schema, real agent names, the 6th tab's actual purpose). Don't ask about anything this brief already answers.
