import { useState } from "react";

// Renders a real product photo when one exists at `src`; falls back to the
// given icon on a soft gradient tile otherwise, so the page still looks
// finished before real photography is dropped into frontend/public/products/.
export function ProductImage({ src, alt, icon: Icon, className = "" }) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div
        className={`flex items-center justify-center bg-gradient-to-br from-signal/10 via-iris/10 to-vital/10 ${className}`}
        role="img"
        aria-label={alt}
      >
        <Icon size={40} strokeWidth={1.5} className="text-signal/70" />
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      onError={() => setFailed(true)}
      className={`object-contain ${className}`}
      loading="lazy"
    />
  );
}
