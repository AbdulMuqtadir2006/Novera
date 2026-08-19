import { useCallback, useEffect, useRef, useState } from "react";
import { getDeviceStatus, getLatestReading, getReadingHistory } from "../lib/api";

const DEVICE_POLL_MS = 5000;
// A new reading can now land from three independent sources (dashboard
// button, WhatsApp Agent, or the device's own periodic auto-send) with no
// client-side signal that it happened — previously the dashboard only ever
// refetched right after the local "Take New Sample" click, so a
// WhatsApp-triggered reading required a manual page refresh to appear.
const READING_POLL_MS = 8000;

export function useLatestReading(refreshKey = 0) {
  const [reading, setReading] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  // Tracks the freshest timestamp seen so the background poll only updates
  // state (and re-renders/re-animates the UI) when something actually
  // changed, not on every idle poll tick.
  const lastTimestampRef = useRef(null);

  const fetchOnce = useCallback((showLoading) => {
    let alive = true;
    if (showLoading) setLoading(true);
    getLatestReading()
      .then((r) => {
        if (!alive) return;
        if (r.timestamp !== lastTimestampRef.current) {
          lastTimestampRef.current = r.timestamp;
          setReading(r);
        }
      })
      .catch((e) => alive && setError(e))
      .finally(() => alive && showLoading && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => fetchOnce(true), [refreshKey, fetchOnce]);

  useEffect(() => {
    const id = setInterval(() => fetchOnce(false), READING_POLL_MS);
    return () => clearInterval(id);
  }, [fetchOnce]);

  return { reading, loading, error };
}

export function useReadingHistory(days = 30, refreshKey = 0) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchOnce = useCallback((showLoading) => {
    let alive = true;
    if (showLoading) setLoading(true);
    getReadingHistory(days)
      .then((h) => alive && setHistory(h))
      .finally(() => alive && showLoading && setLoading(false));
    return () => {
      alive = false;
    };
  }, [days]);

  useEffect(() => fetchOnce(true), [refreshKey, fetchOnce]);

  useEffect(() => {
    const id = setInterval(() => fetchOnce(false), READING_POLL_MS);
    return () => clearInterval(id);
  }, [fetchOnce]);

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
