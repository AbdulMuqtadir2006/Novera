import { useState } from "react";

// Renders a real product photo when one exists at `src`, cropped to fill
// its box edge-to-edge (object-cover, not object-contain — the source
// photos have their own padding/background around the product, so
// "contain" was leaving visible gaps inside the card). Falls back to the
// given icon on a soft gradient tile otherwise, so the page still looks
// finished before real photography exists. Both states get the same
// rounded corners + thin 1px border, so the tile reads as one consistent
// shape whether or not a photo is present.
export function ProductImage({ src, alt, icon: Icon, className = "" }) {
  const [failed, setFailed] = useState(false);

  return (
    <div className={`overflow-hidden rounded-2xl border border-black/10 ${className}`}>
      {!src || failed ? (
        <div
          className="flex h-full w-full items-center justify-center bg-gradient-to-br from-signal/10 via-iris/10 to-vital/10"
          role="img"
          aria-label={alt}
        >
          <Icon size={40} strokeWidth={1.5} className="text-signal/70" />
        </div>
      ) : (
        <img src={src} alt={alt} onError={() => setFailed(true)} className="h-full w-full object-cover" loading="lazy" />
      )}
    </div>
  );
}
