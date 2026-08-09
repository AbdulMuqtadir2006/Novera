import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

// interpolate cyan -> magenta -> purple around the ring
function barColor(tpos) {
  const stops = [
    [40, 207, 224],
    [236, 97, 232],
    [178, 75, 214],
    [40, 207, 224],
  ];
  const seg = tpos * (stops.length - 1);
  const i = Math.floor(seg);
  const f = seg - i;
  const a = stops[i];
  const b = stops[Math.min(i + 1, stops.length - 1)];
  const c = a.map((v, k) => Math.round(v + (b[k] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

const BAR_COUNT = 44;
const RADIUS = 118;

// Positioning (rotate + radial offset) is a plain, never-animated div — a
// literal `transform` string here would otherwise be clobbered by
// framer-motion, which generates its own `transform` from any motion-managed
// scale/rotate style on the same element and overwrites the whole property
// rather than composing with it. `energy` (0..1, real word-boundary-driven,
// see VoiceOrb) reaches each bar as a plain number prop and drives the
// declarative `animate` prop — the same pattern already used everywhere else
// in this app, not an imperative MotionValue.
function Bar({ angle, color, peak, lag, energy, reduced }) {
  return (
    <div
      className="absolute left-1/2 top-1/2 w-[3px]"
      style={{
        height: 26,
        marginLeft: -1.5,
        transform: `rotate(${angle}deg) translateY(-${RADIUS}px)`,
        transformOrigin: "center bottom",
      }}
    >
      <motion.span
        className="block h-full w-full rounded-full"
        style={{
          background: `linear-gradient(to top, ${color}00, ${color})`,
          transformOrigin: "center bottom",
        }}
        animate={{ scaleY: reduced ? 0.24 : 0.24 + energy * peak }}
        transition={{ type: "spring", stiffness: 260, damping: 18 + lag * 20 }}
      />
    </div>
  );
}

function Equalizer({ energy, reduced }) {
  const bars = useMemo(
    () =>
      Array.from({ length: BAR_COUNT }, (_, i) => ({
        angle: (i / BAR_COUNT) * 360,
        color: barColor(i / BAR_COUNT),
        peak: 0.6 + Math.random() * 1.5,
        lag: Math.random(),
      })),
    []
  );
  return (
    <div className="absolute inset-0">
      {bars.map((b, i) => (
        <Bar key={i} {...b} energy={energy} reduced={reduced} />
      ))}
    </div>
  );
}

// Interactive voice-agent orb. Rotating aurora blobs (ambient chrome) + a
// core sphere and circular equalizer whose amplitude is driven by a single
// `energy` value (0..1): kicked up on every real Web Speech `boundary` event
// (`pulseKey` changing) and left to decay back down between words. When no
// boundary events land for a beat (voice/browser without word-boundary
// support) it settles into a slow ambient breathing state instead of
// freezing dead, so silence-vs-no-signal isn't misread as "broken."
export function VoiceOrb({ active, pulseKey = 0 }) {
  const reduced = usePrefersReducedMotion();
  const [energy, setEnergy] = useState(0);
  const lastPulseAt = useRef(0);

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

      <Equalizer energy={energy} reduced={reduced} />

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
