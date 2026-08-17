import { metricMeta, statusMeta, formatValue } from "../../lib/format";
import { healthAreas } from "../../data/healthAreas";

// Compose a spoken *screening summary* (not a diagnosis) from the latest
// reading — same data source as the Dashboard.
export function buildVoiceScript(reading) {
  if (!reading) return "";
  const parts = [];
  parts.push(
    "Here's your Novera screening summary. This is a research-stage overview, not a medical diagnosis."
  );

  const metricSentences = Object.keys(metricMeta).map((key) => {
    const m = reading.metrics[key];
    const label = metricMeta[key].label;
    const value = formatValue(m.value, metricMeta[key].dp);
    const unit = m.unit ? ` ${m.unit}` : "";
    const state = statusMeta[m.status].label.toLowerCase();
    return `${label} reads ${value}${unit}, which is ${state}.`;
  });
  parts.push("Across your four biomarkers: " + metricSentences.join(" "));

  const watch = healthAreas.filter(
    (a) => reading.healthAreas[a.id] !== "good"
  );
  if (watch.length === 0) {
    parts.push(
      "All four health areas — kidney, hydration, oral, and digestive — are looking steady."
    );
  } else {
    const names = watch.map((a) => a.name).join(", ");
    parts.push(
      `Most of your health areas look steady. The ones worth a closer look are: ${names}. You'll find specific suggestions on your Natural Recovery page.`
    );
  }

  parts.push(
    "Remember, Novera is built to explore what saliva can tell us — for anything concerning, check with a medical professional."
  );
  return parts.join(" ");
}
