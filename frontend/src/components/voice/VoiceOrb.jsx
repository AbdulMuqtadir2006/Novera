import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

const SIZE = 288; // matches h-72 w-72
const CENTER = SIZE / 2;
const BASE_R = 118;
const POINTS = 120; // enough segments that straight lines already read as a smooth curve

// A closed polar curve r(θ) = BASE_R + energy * Σ harmonic sine waves. Summing
// a handful of fixed-phase sinusoids gives a naturally smooth, organic
// wobble with no per-point smoothing math needed — at energy 0 it's a
// perfect circle, exactly centered (unlike the old radial-bar version, whose
// rotate+translate math pivoted around each bar's *bottom* edge instead of
// the sphere's true center).
function makeHarmonics() {
  return Array.from({ length: 4 }, () => ({
    freq: 2 + Math.floor(Math.random() * 4), // 2..5 lobes
    amp: 9 + Math.random() * 16, // px, before the energy scale — sized to read as clearly reactive at energy 1, not a faint ripple
    phase: Math.random() * Math.PI * 2,
  }));
}

function buildPath(harmonics, energy) {
  let d = "";
  for (let i = 0; i <= POINTS; i++) {
    const theta = (i / POINTS) * Math.PI * 2;
    let r = BASE_R;
    for (const h of harmonics) r += energy * h.amp * Math.sin(h.freq * theta + h.phase);
    const x = CENTER + r * Math.cos(theta);
    const y = CENTER + r * Math.sin(theta);
    d += `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)} `;
  }
  return d + "Z";
}

// Circular waveform ring — replaces the old 44-bar equalizer. `energyRef` is
// read every animation frame (not React state) so the curve eases smoothly
// toward the real energy target via direct DOM mutation, the same
// rAF-driven pattern AmbientBackground already uses elsewhere in this app,
// rather than relying on per-render React updates.
function CircularWave({ energyRef, reduced }) {
  const pathRef = useRef(null);
  const displayRef = useRef(0);
  const harmonics = useMemo(makeHarmonics, []);

  useEffect(() => {
    if (!pathRef.current) return;
    if (reduced) {
      pathRef.current.setAttribute("d", buildPath(harmonics, 0));
      return;
    }
    let raf;
    const tick = () => {
      displayRef.current += (energyRef.current - displayRef.current) * 0.12;
      pathRef.current.setAttribute("d", buildPath(harmonics, displayRef.current));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [reduced, harmonics, energyRef]);

  return (
    <svg
      width={SIZE}
      height={SIZE}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="absolute inset-0 overflow-visible"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="voiceWaveGradient" x1="0" y1="0" x2={SIZE} y2={SIZE} gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#28CFE0" />
          <stop offset="50%" stopColor="#EC61E8" />
          <stop offset="100%" stopColor="#B24BD6" />
        </linearGradient>
      </defs>
      <path
        ref={pathRef}
        fill="none"
        stroke="url(#voiceWaveGradient)"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity={0.85}
      />
    </svg>
  );
}

// Interactive voice-agent orb. Rotating aurora blobs (ambient chrome) + a
// core sphere and a circular waveform ring whose amplitude is driven by a
// single `energy` value (0..1): kicked up on every real Web Speech
// `boundary` event (`pulseKey` changing) and left to decay back down
// between words. When no boundary events land for a beat (voice/browser
// without word-boundary support) it settles into a slow ambient breathing
// state instead of freezing dead, so silence-vs-no-signal isn't misread as
// "broken."
export function VoiceOrb({ active, pulseKey = 0 }) {
  const reduced = usePrefersReducedMotion();
  const [energy, setEnergy] = useState(0);
  const energyRef = useRef(0);
  const lastPulseAt = useRef(0);

  useEffect(() => {
    energyRef.current = energy;
  }, [energy]);

  useEffect(() => {
    if (!active) return;
    lastPulseAt.current = performance.now();
    setEnergy(1);
    const t = setTimeout(() => setEnergy(0.16), 100);
    return () => clearTimeout(t);
  }, [pulseKey, active]);

  useEffect(() => {
    if (!active) {
      setEnergy(0);
      return;
    }
    const id = setInterval(() => {
      if (performance.now() - lastPulseAt.current > 1200 && !reduced) {
        setEnergy(0.3);
        setTimeout(() => setEnergy(0.14), 700);
      }
    }, 1400);
    return () => clearInterval(id);
  }, [active, reduced]);

  return (
    <div className="relative grid h-72 w-72 place-items-center">
      {/* rotating aurora — ambient chrome, not audio-reactive */}
      {[
        { c: "bg-vital", x: -18, y: -14, dir: 1, base: 0.34 },
        { c: "bg-signal", x: 20, y: 10, dir: -1, base: 0.32 },
        { c: "bg-iris", x: -4, y: 20, dir: 1, base: 0.26 },
      ].map((b, i) => (
        <motion.div
          key={i}
          className={`absolute h-40 w-40 rounded-full ${b.c} blur-3xl`}
          style={{ x: b.x, y: b.y }}
          animate={
            reduced
              ? { opacity: b.base }
              : {
                  rotate: b.dir * 360,
                  scale: active ? [1, 1.22, 1] : [1, 1.06, 1],
                  opacity: active ? b.base + 0.22 : b.base,
                }
          }
          transition={{
            rotate: { duration: 14 + i * 5, repeat: Infinity, ease: "linear" },
            scale: { duration: active ? 1.6 : 5, repeat: Infinity, ease: "easeInOut" },
            opacity: { duration: 0.6 },
          }}
        />
      ))}

      {/* sonar ring — amplitude tied to real energy, not a fixed loop */}
      {!reduced && active && (
        <motion.span
          className="absolute rounded-full border border-signal/40"
          style={{ width: 132, height: 132 }}
          animate={{ scale: [1, 1.15 + energy * 0.55], opacity: [0.5, 0] }}
          transition={{ duration: 0.6, ease: "easeOut", repeat: Infinity, repeatDelay: 0.2 }}
        />
      )}

      <CircularWave energyRef={energyRef} reduced={reduced} />

      {/* core sphere */}
      <motion.div
        className="relative grid h-28 w-28 place-items-center rounded-full"
        style={{
          background:
            "radial-gradient(circle at 34% 28%, #7ef0ff, #28CFE0 34%, #B24BD6 72%, #EC61E8 100%)",
          boxShadow: "0 0 60px -6px rgba(40,207,224,0.55), inset 0 -10px 26px -8px rgba(11,8,25,0.55)",
        }}
        animate={
          reduced
            ? { scale: 1, opacity: 1 }
            : { scale: 1 + energy * 0.16, opacity: 0.55 + energy * 0.45 }
        }
        transition={{ type: "spring", stiffness: 260, damping: 22 }}
      >
        {/* inner waveform — same energy signal, smaller amplitude */}
        <div className="flex items-end gap-[3px]">
          {[0.55, 0.9, 0.68, 1, 0.72, 0.85].map((h, i) => (
            <motion.span
              key={i}
              className="w-[3px] rounded-full bg-white/90"
              animate={{ height: reduced ? 10 : 10 + h * 30 * energy }}
              transition={{ type: "spring", stiffness: 300, damping: 20 }}
            />
          ))}
        </div>
      </motion.div>
    </div>
  );
}
