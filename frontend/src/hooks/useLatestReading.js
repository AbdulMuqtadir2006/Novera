import { useEffect, useState } from "react";
import { getLatestReading, getReadingHistory } from "../lib/api";

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
