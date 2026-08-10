import { useEffect, useState } from "react";
import { getDeviceStatus, getLatestReading, getReadingHistory } from "../lib/api";

const DEVICE_POLL_MS = 5000;

export function useLatestReading(refreshKey = 0) {
  const [reading, setReading] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getLatestReading()
      .then((r) => alive && setReading(r))
      .catch((e) => alive && setError(e))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [refreshKey]);

  return { reading, loading, error };
}

export function useReadingHistory(days = 30, refreshKey = 0) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getReadingHistory(days)
      .then((h) => alive && setHistory(h))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [days, refreshKey]);

  return { history, loading };
}

// Polls the ESP32's last heartbeat so the dashboard can show live
// connected/offline + which WiFi network it's on.
export function useDeviceStatus() {
  const [status, setStatus] = useState({ online: false, ssid: null });

  useEffect(() => {
    let alive = true;
    const poll = () => {
      getDeviceStatus()
        .then((s) => alive && setStatus(s))
        .catch(() => alive && setStatus({ online: false, ssid: null }));
    };
    poll();
    const id = setInterval(poll, DEVICE_POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return status;
}
