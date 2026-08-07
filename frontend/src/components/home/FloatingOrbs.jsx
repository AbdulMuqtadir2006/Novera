import { useEffect, useRef } from "react";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

// Many soft white glowing orbs drifting + bobbing over the dark hero.
function makeOrb(w, h) {
  const small = Math.random() < 0.8;
  const r = small ? 1.2 + Math.random() * 3.5 : 6 + Math.random() * 12;
  return {
    x: Math.random() * w,
    y: Math.random() * h,
    r,
    baseAlpha: (small ? 0.28 : 0.14) + Math.random() * 0.35,
    vx: (Math.random() - 0.5) * 0.16,
    vy: -0.05 - Math.random() * 0.22,
    bobAmp: 6 + Math.random() * 18,
    bobSpeed: 0.3 + Math.random() * 0.8,
    twPhase: Math.random() * Math.PI * 2,
    twSpeed: 0.4 + Math.random() * 1.2,
  };
}

export function FloatingOrbs({
  className = "pointer-events-none absolute inset-0 z-10 h-full w-full",
}) {
  const canvasRef = useRef(null);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w = 0;
    let h = 0;
    let orbs = [];

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // Floor keeps phone screens from reading as sparse — orb count would
      // otherwise scale down to ~20 on a typical portrait viewport vs. ~90
      // on desktop, even though the same density feel is wanted on both.
      const count = Math.max(45, Math.min(90, Math.round((w * h) / 16000)));
      orbs = Array.from({ length: count }, () => makeOrb(w, h));
    };

    const draw = (o, alpha, x, y) => {
      const glow = o.r * 4.5;
      const g = ctx.createRadialGradient(x, y, 0, x, y, glow);
      g.addColorStop(0, `rgba(255,255,255,${alpha})`);
      g.addColorStop(0.35, `rgba(230,245,255,${alpha * 0.5})`);
      g.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(x, y, glow, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = `rgba(255,255,255,${Math.min(1, alpha * 1.6)})`;
      ctx.beginPath();
      ctx.arc(x, y, o.r * 0.55, 0, Math.PI * 2);
      ctx.fill();
    };

    let raf = 0;
    let t = 0;

    const frame = () => {
      t += 0.016;
      ctx.clearRect(0, 0, w, h);
      for (const o of orbs) {
        o.x += o.vx;
        o.y += o.vy;
        if (o.y < -20) { o.y = h + 20; o.x = Math.random() * w; }
        if (o.x < -20) o.x = w + 20;
        if (o.x > w + 20) o.x = -20;
        const bob = Math.sin(t * o.bobSpeed + o.twPhase) * o.bobAmp;
        const tw = 0.6 + 0.4 * Math.sin(t * o.twSpeed + o.twPhase);
        draw(o, o.baseAlpha * tw, o.x, o.y + bob);
      }
      raf = requestAnimationFrame(frame);
    };

    resize();
    window.addEventListener("resize", resize);
    if (reduced) {
      ctx.clearRect(0, 0, w, h);
      for (const o of orbs) draw(o, o.baseAlpha, o.x, o.y);
    } else {
      raf = requestAnimationFrame(frame);
    }

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, [reduced]);

  return <canvas ref={canvasRef} aria-hidden="true" className={className} />;
}
