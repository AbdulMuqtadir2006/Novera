import { Wifi, WifiOff } from "lucide-react";
import { useDeviceStatus } from "../../hooks/useLatestReading";
import { useLang } from "../../i18n/LanguageContext";

// Shows whether the ESP32 sensor node has heartbeated recently, and which
// WiFi network it's currently on.
export function DeviceStatusBadge() {
  const { t } = useLang();
  const { online, ssid } = useDeviceStatus();
  // Red (not the old muted gray) for offline, 2026-08-26, Hassan's call —
  // makes it visually unmistakable that a reading came from a random/demo
  // generator (e.g. the admin account's instant "Take New Sample") and not
  // a real connected sensor, rather than reading as a quiet neutral status.
  const color = online ? "#16a34a" : "#ef4444";

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold"
      style={{ backgroundColor: `${color}1f`, color }}
    >
      <span className="relative flex h-2 w-2">
        {online && (
          <span
            className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60"
            style={{ backgroundColor: color }}
          />
        )}
        <span className="relative inline-flex h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      </span>
      {online ? <Wifi size={13} /> : <WifiOff size={13} />}
      {online ? `${t("device.connected")} · ${ssid}` : t("device.offline")}
    </span>
  );
}
