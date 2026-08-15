import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

// GSAP's documented fix for scroll-linked animation jank on mobile — without
// it, iOS/Android address-bar show/hide during scroll causes ScrollTrigger's
// pinned sections to visibly lag or stutter before catching up. Safe to call
// once globally; guarded so remounting the hero doesn't re-invoke it.
let scrollNormalized = false;
function normalizeScrollOnce() {
  if (scrollNormalized || typeof window === "undefined") return;
  scrollNormalized = true;
  ScrollTrigger.normalizeScroll(true);
}

const TOTAL_FRAMES = 240;

// Tier-1 (priority) loading: every 8th frame gives full-range scroll
// coverage at coarse granularity almost immediately, instead of finishing
// the first N frames while the rest of the range stays blank. 240 is added
// explicitly since the frame 240 is what the reduced-motion path holds on.
const PRIORITY_STRIDE = 8;
// Safety net so a couple of slow/failed tier-1 requests can't block the
// hero forever — same "don't stall on one bad frame" philosophy as the
// per-image onerror handler below.
const PRIORITY_TIMEOUT_MS = 4500;
// Tier-2 (background) loading: fill in the remaining frames behind a small
// concurrency cap rather than firing ~210 more requests simultaneously.
const BACKGROUND_CONCURRENCY = 6;

function isSmallScreen() {
  return typeof window !== "undefined" && window.matchMedia("(max-width: 767px)").matches;
}

// Small screens get a dedicated portrait (720x1280) frame set — cropped for
// the phone aspect ratio rather than cover-cropped from the desktop
// landscape (1280x720) set, which loses most of the frame's width.
const getFramePath = (n, mobile) =>
  `${mobile ? "/frames-mobile" : "/frames"}/frame_${String(n).padStart(4, "0")}.jpg`;

// Build the list of frame numbers actually used. Both sets ship all 240
// frames — the mobile set is already sized for phone bandwidth, so no
// frame-skipping is needed there.
function buildFrameList() {
  const list = [];
  for (let n = 1; n <= TOTAL_FRAMES; n++) list.push(n);
  return list;
}

// Coarse, full-range subset loaded first and gates `ready`.
function buildPriorityFrameNums() {
  const list = [];
  for (let n = 1; n <= TOTAL_FRAMES; n += PRIORITY_STRIDE) list.push(n);
  if (list[list.length - 1] !== TOTAL_FRAMES) list.push(TOTAL_FRAMES);
  return list;
}

/**
 * Pins the hero section and scrubs a <canvas> through the frame sequence as the
 * user scrolls. Returns preload + progress state so the caption layer can
 * narrate the formation.
 *
 * When `enabled` is false (prefers-reduced-motion), no ScrollTrigger is created;
 * the final frame is drawn statically once it loads.
 */
export function useScrollFrameSequence(canvasRef, sectionRef, enabled = true) {
  const imagesRef = useRef([]);
  const frameNumsRef = useRef([]);
  const [ready, setReady] = useState(false);
  const [loadProgress, setLoadProgress] = useState(0); // 0..1 overall preload (tier 1 + tier 2)
  const [readyProgress, setReadyProgress] = useState(0); // 0..1 progress toward `ready` (tier 1 only)
  const [progress, setProgress] = useState(0); // 0..1 scroll position

  // Preload frames: tier 1 (priority) blocks readiness, tier 2 (background,
  // concurrency-limited) fills in the rest afterward. `draw()`/`drawCover()`
  // already no-op on a not-yet-loaded frame and leave the previous frame on
  // screen, so tier 2 needs no explicit "swap in" step — an `img.complete`
  // check next time that index is drawn picks it up automatically.
  useEffect(() => {
    const mobile = isSmallScreen();
    const frameNums = buildFrameList();
    frameNumsRef.current = frameNums;
    const count = frameNums.length;
    const priorityNums = new Set(buildPriorityFrameNums());
    const priorityCount = priorityNums.size;

    let loaded = 0;
    let priorityLoaded = 0;
    let cancelled = false;
    let readyFired = false;

    const fireReady = () => {
      if (readyFired) return;
      readyFired = true;
      clearTimeout(timeoutId);
      setReady(true);
    };

    const timeoutId = setTimeout(fireReady, PRIORITY_TIMEOUT_MS);

    const images = frameNums.map(() => {
      const img = new Image();
      img.decoding = "async";
      return img;
    });
    imagesRef.current = images;

    let inFlight = 0;
    const backgroundIndexes = [];

    const loadFrame = (index, isPriority) => {
      const img = images[index];
      const done = () => {
        if (cancelled) return;
        loaded += 1;
        setLoadProgress(loaded / count);
        if (isPriority) {
          priorityLoaded += 1;
          // Progress toward readiness, not overall load — this is the only
          // phase the preload UI is on screen for, so it should read 0→100%
          // rather than stall around ~13% (tier 1's share of all 240).
          setReadyProgress(priorityLoaded / priorityCount);
          if (priorityLoaded === priorityCount) fireReady();
        } else {
          inFlight -= 1;
          pumpBackground();
        }
      };
      img.onload = done;
      img.onerror = done; // don't stall on one bad frame
      img.src = getFramePath(frameNums[index], mobile);
    };

    function pumpBackground() {
      if (cancelled) return;
      while (nextBackground < backgroundIndexes.length && inFlight < BACKGROUND_CONCURRENCY) {
        inFlight += 1;
        loadFrame(backgroundIndexes[nextBackground++], false);
      }
    }
    let nextBackground = 0;

    frameNums.forEach((n, index) => {
      if (priorityNums.has(n)) {
        loadFrame(index, true);
      } else {
        backgroundIndexes.push(index);
      }
    });
    pumpBackground();

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, []);

  // Draw + wire ScrollTrigger.
  useEffect(() => {
    if (!ready || !canvasRef.current || !sectionRef.current) return;
    normalizeScrollOnce();
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d", { alpha: false });
    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let cssW = 0;
    let cssH = 0;

    const imgs = imagesRef.current;
    const lastIndex = imgs.length - 1;

    // cover-fit: fill the canvas, cropping overflow, preserving aspect ratio.
    // Rounds the larger dimension up (with a 1px overscan) so float rounding
    // never leaves a sliver of canvas undrawn — alpha:false defaults undrawn
    // pixels to solid black, which reads as a stray line against the page's
    // navy (#080919) background rather than blending in.
    const drawCover = (img) => {
      if (!img || !img.complete || !img.naturalWidth) return;
      const cw = cssW;
      const ch = cssH;
      const ir = img.naturalWidth / img.naturalHeight;
      const cr = cw / ch;
      let dw, dh, dx, dy;
      if (cr > ir) {
        dw = cw + 1;
        dh = Math.ceil(dw / ir);
        dx = -0.5;
        dy = (ch - dh) / 2;
      } else {
        dh = ch + 1;
        dw = Math.ceil(dh * ir);
        dx = (cw - dw) / 2;
        dy = -0.5;
      }
      ctx.fillStyle = "#080919";
      ctx.fillRect(0, 0, cw, ch);
      ctx.drawImage(img, dx, dy, dw, dh);
    };

    let currentIndex = -1;
    const draw = (index) => {
      const clamped = Math.max(0, Math.min(lastIndex, index));
      if (clamped === currentIndex) return;
      currentIndex = clamped;
      drawCover(imgs[clamped]);
    };

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      cssW = window.innerWidth;
      cssH = window.innerHeight;
      canvas.width = Math.round(cssW * dpr);
      canvas.height = Math.round(cssH * dpr);
      canvas.style.width = `${cssW}px`;
      canvas.style.height = `${cssH}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // High-quality resampling — resetting the canvas size clears these, so
      // they must be re-applied on every resize.
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      currentIndex = -1;
      draw(Math.round(progress * lastIndex));
    };

    resize();
    window.addEventListener("resize", resize);

    // Reduced motion / disabled: hold on the final assembled frame. Frame
    // TOTAL_FRAMES is in tier 1, so it's normally already loaded by the time
    // `ready` flips — but the priority-timeout safety net can in principle
    // fire `ready` before it lands, so fall back to waiting on that one
    // image specifically rather than risk drawing nothing.
    if (!enabled) {
      const lastImg = imgs[lastIndex];
      const showLastFrame = () => {
        draw(lastIndex);
        setProgress(1);
      };
      if (lastImg.complete && lastImg.naturalWidth) {
        showLastFrame();
      } else {
        lastImg.addEventListener("load", showLastFrame, { once: true });
      }
      return () => {
        lastImg.removeEventListener("load", showLastFrame);
        window.removeEventListener("resize", resize);
      };
    }

    let rafId = 0;
    const trigger = ScrollTrigger.create({
      trigger: sectionRef.current,
      start: "top top",
      end: "+=400%",
      pin: true,
      // true (not a number) ties the frame index exactly to scroll position
      // with zero catch-up delay — a fractional value like 0.5 deliberately
      // lags the animation behind the scrollbar, which read as "kicks in
      // after a moment" rather than tracking the finger immediately.
      scrub: true,
      onUpdate: (self) => {
        setProgress(self.progress);
        if (rafId) return;
        rafId = requestAnimationFrame(() => {
          rafId = 0;
          draw(Math.round(self.progress * lastIndex));
        });
      },
    });

    return () => {
      trigger.kill();
      if (rafId) cancelAnimationFrame(rafId);
      window.removeEventListener("resize", resize);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, enabled]);

  return { ready, progress, loadProgress, readyProgress };
}
