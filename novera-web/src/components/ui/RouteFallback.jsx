// Lightweight suspense fallback shown while a lazy route chunk loads.
export function RouteFallback() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-mist">
      <div className="flex flex-col items-center gap-4">
        <span className="relative flex h-10 w-10">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal/40" />
          <span className="relative inline-flex h-10 w-10 rounded-full border-2 border-signal/30 border-t-signal animate-spin" />
        </span>
        <span className="font-mono text-xs uppercase tracking-[0.24em] text-depth/50">
          Loading
        </span>
      </div>
    </div>
  );
}
