export const metricMeta = {
  ph: { label: "pH", dp: 2 },
  creatinine: { label: "Creatinine", dp: 2 },
  urea: { label: "Urea", dp: 1 },
  temperature: { label: "Temperature", dp: 1 },
};

export const statusMeta = {
  good: { label: "In range", color: "#3DDC97", token: "status-good" },
  watch: { label: "Watch", color: "#F2A93E", token: "status-watch" },
  attention: { label: "Attention", color: "#FF5D5D", token: "status-attention" },
};

export function formatTimestamp(iso) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatDateShort(iso) {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export function formatValue(value, dp) {
  return Number(value).toFixed(dp);
}
