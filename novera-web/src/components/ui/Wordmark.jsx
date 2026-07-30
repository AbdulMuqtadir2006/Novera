// Novera wordmark — the real logo mark (magenta→purple→cyan vortex) + name.
// `tone` switches the text colour between the dark hero and the light subpages.
export function Wordmark({ tone = "light", className = "" }) {
  const text = tone === "dark" ? "text-depth" : "text-white";
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <img
        src="/logo-mark.png"
        alt=""
        aria-hidden="true"
        className="h-9 w-9 select-none object-contain"
        draggable="false"
      />
      <span className={`font-display text-xl font-bold tracking-tight ${text}`}>
        Novera
      </span>
    </span>
  );
}
