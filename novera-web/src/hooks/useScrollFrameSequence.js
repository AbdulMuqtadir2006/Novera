import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const TOTAL_FRAMES = 240;
const getFramePath = (n) => `/frames/frame_${String(n).padStart(4, "0")}.jpg`;

// Build the list of frame numbers actually used. On small screens we sample
// every second frame to halve the preload weight (brief §4.1 fallback).
function buildFrameList() {
  const isSmall =
    typeof window !== "undefined" && window.matchMedia("(max-width: 767px)").matches;
  const step = isSmall ? 2 : 1;
  const list = [];
  for (let n = 1; n <= TOTAL_FRAMES; n += step) list.push(n);
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
  const [loadProgress, setLoadProgress] = useState(0); // 0..1 preload
  const [progress, setProgress] = useState(0); // 0..1 scroll position

  // Preload frames.
  useEffect(() => {
    const frameNums = buildFrameList();
    frameNumsRef.current = frameNums;
    const count = frameNums.length;
    let loaded = 0;
    let cancelled = false;

    imagesRef.current = frameNums.map((n) => {
      const img = new Image();
      img.decoding = "async";
      img.src = getFramePath(n);
      const done = () => {
        if (cancelled) return;
        loaded += 1;
        setLoadProgress(loaded / count);
        if (loaded === count) setReady(true);
      };
      img.onload = done;
      img.onerror = done; // don't stall the whole hero on one bad frame
      return img;
    });

    return () => {
      cancelled = true;
    };
  }, []);

  // Draw + wire ScrollTrigger.
  useEffect(() => {
    if (!ready || !canvasRef.current || !sectionRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d", { alpha: false });
    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let cssW = 0;
    let cssH = 0;

    const imgs = imagesRef.current;
    const lastIndex = imgs.length - 1;

    // cover-fit: fill the canvas, cropping overflow, preserving aspect ratio.
    const drawCover = (img) => {
      if (!img || !img.complete || !img.naturalWidth) return;
      const cw = cssW;
      const ch = cssH;
      const ir = img.naturalWidth / img.naturalHeight;
      const cr = cw / ch;
      let dw, dh, dx, dy;
      if (cr > ir) {
        dw = cw;
        dh = cw / ir;
        dx = 0;
        dy = (ch - dh) / 2;
      } else {
        dh = ch;
        dw = ch * ir;
        dx = (cw - dw) / 2;
        dy = 0;
      }
      ctx.clearRect(0, 0, cw, ch);
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

    // Reduced motion / disabled: hold on the final assembled frame.
    if (!enabled) {
      draw(lastIndex);
      setProgress(1);
      return () => window.removeEventListener("resize", resize);
    }

    let rafId = 0;
    const trigger = ScrollTrigger.create({
      trigger: sectionRef.current,
      start: "top top",
      end: "+=400%",
      pin: true,
      scrub: 0.5,
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

  return { ready, progress, loadProgress };
}
