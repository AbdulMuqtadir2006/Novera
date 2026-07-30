import { useEffect, useRef } from "react";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

// Brand-coloured "stars": mostly cyan/magenta, some purple + soft white.
const COLORS = [
  [40, 207, 224], // signal cyan
  [40, 207, 224],
  [236, 97, 232], // vital magenta
  [236, 97, 232],
  [178, 75, 214], // iris purple
  [180, 200, 255], // soft white-blue
];

function makeParticle(w, h) {
  const c = COLORS[(Math.random() * COLORS.length) | 0];
  return {
    x: Math.random() * w,
    y: Math.random() * h,
    r: 0.7 + Math.random() * 2.1,
    color: c,
    baseAlpha: 0.12 + Math.random() * 0.32,
    twPhase: Math.random() * Math.PI * 2,
    twSpeed: 0.4 + Math.random() * 1.1,
    vx: (Math.random() - 0.5) * 0.14,
    vy: -0.06 - Math.random() * 0.16, // gentle upward drift
    depth: 0.3 + Math.random() * 0.7, // for mouse parallax
  };
}

/**
 * Animated ambient backdrop for the app pages: a soft mist base, slow drifting
 * brand-coloured glow blobs, and a canvas starfield of twinkling, drifting
 * glows. Fixed to the viewport so content scrolls over it. Content sits on
 * solid cards, so readability is preserved. Static under prefers-reduced-motion.
 */
export function AmbientBackground() {
  const canvasRef = useRef(null);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w = 0;
    let h = 0;
    let particles = [];
    const mouse = { x: 0, y: 0, tx: 0, ty: 0 };

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.min(96, Math.round((w * h) / 20000));
      particles = Array.from({ length: count }, () => makeParticle(w, h));
    };

    const onMouse = (e) => {
      mouse.tx = (e.clientX / w - 0.5) * 2;
      mouse.ty = (e.clientY / h - 0.5) * 2;
    };

    const drawParticle = (p, alpha, px, py) => {
      const [r, g, b] = p.color;
      const glow = p.r * 6;
      const grad = ctx.createRadialGradient(px, py, 0, px, py, glow);
      grad.addColorStop(0, `rgba(${r},${g},${b},${alpha})`);
      grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(px, py, glow, 0, Math.PI * 2);
      ctx.fill();
      // bright core
      ctx.fillStyle = `rgba(${r},${g},${b},${Math.min(1, alpha * 1.8)})`;
      ctx.beginPath();
      ctx.arc(px, py, p.r * 0.6, 0, Math.PI * 2);
      ctx.fill();
    };

    let raf = 0;
    let t = 0;

    const staticFrame = () => {
      ctx.clearRect(0, 0, w, h);
      for (const p of particles) drawParticle(p, p.baseAlpha, p.x, p.y);
    };

    const frame = () => {
      t += 0.016;
      mouse.x += (mouse.tx - mouse.x) * 0.04;
      mouse.y += (mouse.ty - mouse.y) * 0.04;
      ctx.clearRect(0, 0, w, h);
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.y < -10) p.y = h + 10;
        if (p.x < -10) p.x = w + 10;
        if (p.x > w + 10) p.x = -10;
        const tw = 0.55 + 0.45 * Math.sin(t * p.twSpeed + p.twPhase);
        const px = p.x + mouse.x * 16 * p.depth;
        const py = p.y + mouse.y * 16 * p.depth;
        drawParticle(p, p.baseAlpha * tw, px, py);
      }
      raf = requestAnimationFrame(frame);
    };

    resize();
    window.addEventListener("resize", resize);
    if (reduced) {
      staticFrame();
    } else {
      window.addEventListener("mousemove", onMouse);
      raf = requestAnimationFrame(frame);
    }

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMouse);
    };
  }, [reduced]);

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      {/* mist base with a touch of depth toward the edges */}
      <div className="absolute inset-0 bg-mist" />
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(130% 90% at 50% 0%, rgba(178,75,214,0.06), transparent 55%), radial-gradient(120% 90% at 100% 100%, rgba(40,207,224,0.06), transparent 55%)",
        }}
      />
      {/* slow drifting glow blobs */}
      <div className="absolute -left-32 top-24 h-[380px] w-[380px] animate-drift-a rounded-full bg-signal/[0.10] blur-[120px]" />
      <div className="absolute -right-32 top-1/2 h-[420px] w-[420px] animate-drift-b rounded-full bg-vital/[0.09] blur-[120px]" />
      <div className="absolute bottom-0 left-1/3 h-[340px] w-[340px] animate-float rounded-full bg-iris/[0.08] blur-[120px]" />
      {/* twinkling starfield */}
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
    </div>
  );
}
