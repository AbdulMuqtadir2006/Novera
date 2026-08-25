import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Images } from "lucide-react";

const AUTO_ADVANCE_MS = 4000;

// Auto-advancing crossfade slideshow. Pauses on hover (desktop) so a visitor
// reading a caption doesn't have the photo change under them. Renders an
// honest empty-state card — never a broken image — when `images` is empty,
// since the homepage showcase this backs (see data/showcase.js) ships with
// no real photos yet.
export function ImageSlideshow({ images = [], emptyIcon: EmptyIcon = Images, emptyLabel = "Photos coming soon", className = "" }) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (images.length < 2 || paused) return;
    const id = setInterval(() => setIndex((i) => (i + 1) % images.length), AUTO_ADVANCE_MS);
    return () => clearInterval(id);
  }, [images.length, paused]);

  // Clamp in case `images` shrinks (e.g. hot-reload during editing) while
  // `index` pointed past the new end.
  const safeIndex = images.length ? index % images.length : 0;

  if (images.length === 0) {
    return (
      <div
        className={`flex aspect-[4/3] w-full flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-white/15 bg-white/[0.02] text-slate-500 ${className}`}
      >
        <EmptyIcon size={28} strokeWidth={1.5} />
        <span className="text-xs font-medium">{emptyLabel}</span>
      </div>
    );
  }

  return (
    <div className={className}>
      <div
        className="relative aspect-[4/3] w-full overflow-hidden rounded-2xl border border-white/10 bg-ink/40"
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
      >
        {/* object-contain, not object-cover (2026-08-25) — real photos here
            range from portrait (0.7) to wide landscape (1.78), and cropping
            to fill a fixed box would cut people/content out of several of
            them. Always shows the whole photo; bg-ink/40 above fills
            whatever letterbox space is left. */}
        <AnimatePresence mode="wait">
          <motion.img
            key={images[safeIndex].src}
            src={images[safeIndex].src}
            alt={images[safeIndex].alt || ""}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.6, ease: "easeInOut" }}
            className="absolute inset-0 h-full w-full object-contain"
          />
        </AnimatePresence>
      </div>

      {/* Dots live below the frame, not overlaid on it — with object-contain
          a portrait photo can reach the bottom edge of the box, so an
          overlaid dot strip would sit on top of real photo content. */}
      {images.length > 1 && (
        <div className="mt-3 flex items-center justify-center gap-1.5">
          {images.map((_, i) => (
            <button
              key={i}
              type="button"
              aria-label={`Show photo ${i + 1}`}
              onClick={() => setIndex(i)}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                i === safeIndex ? "w-5 bg-signal" : "w-1.5 bg-white/30 hover:bg-white/50"
              }`}
            />
          ))}
        </div>
      )}
    </div>
  );
}
