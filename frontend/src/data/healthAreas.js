import { Filter, Droplets, Smile, Activity } from "lucide-react";

// Health areas — copy is used verbatim per brief §4.4.
export const healthAreas = [
  {
    id: "kidney",
    name: "Kidney Health",
    icon: Filter,
    copy: "Monitor biomarkers that may indicate kidney function changes over time.",
  },
  {
    id: "hydration",
    name: "Hydration",
    icon: Droplets,
    copy: "Track hydration balance through saliva-based hydration index.",
  },
  {
    id: "oral",
    name: "Oral Health",
    icon: Smile,
    copy: "Detect early oral protein indicators for proactive dental wellness.",
  },
  {
    id: "digestive",
    name: "Digestive Health",
    icon: Activity,
    copy: "Observe salivary markers related to digestive system function.",
  },
];

export const healthAreaById = Object.fromEntries(
  healthAreas.map((a) => [a.id, a])
);

// Rule-based self-care guidance keyed by area + status (brief §8).
export const selfCareTips = {
  kidney: {
    good: {
      title: "Kidney signals look steady",
      tip: "Your kidney-related markers sit within their reference ranges. Keep a consistent fluid intake and revisit after your next sample.",
    },
    watch: {
      title: "Give your kidneys an easy day",
      tip: "Urea and creatinine are trending toward the upper edge. Favour water over salty or heavily processed food today, and space out protein-heavy meals.",
    },
    attention: {
      title: "Worth a closer look",
      tip: "Kidney-related markers are outside the reference range. This is a screening signal, not a diagnosis — consider discussing it with a clinician if it persists.",
    },
  },
  hydration: {
    good: {
      title: "Hydration is on track",
      tip: "Your saliva hydration index looks balanced. Sip steadily through the day rather than in large bursts to keep it there.",
    },
    watch: {
      title: "Top up your water",
      tip: "Your hydration index reads a little low. Aim for a glass of water now and one with each meal — small, regular amounts absorb best.",
    },
    attention: {
      title: "Rehydrate deliberately",
      tip: "Hydration markers are notably low. Drink water steadily over the next few hours and add an electrolyte source if you've been active or in heat.",
    },
  },
  oral: {
    good: {
      title: "Oral markers look healthy",
      tip: "Salivary pH and protein indicators are in a comfortable range. Keep up your brushing and flossing rhythm.",
    },
    watch: {
      title: "Mind your oral pH",
      tip: "Your salivary pH is drifting from neutral. Rinse with water after acidic or sugary food and wait ~30 minutes before brushing to protect enamel.",
    },
    attention: {
      title: "Oral chemistry needs attention",
      tip: "Oral markers are outside the usual range. A dental check-up can rule out anything that a saliva screen can only hint at.",
    },
  },
  digestive: {
    good: {
      title: "Digestive markers are calm",
      tip: "Salivary markers related to digestion look settled. Regular meals and fibre keep this steady.",
    },
    watch: {
      title: "Ease the load on digestion",
      tip: "Some digestive-related markers are slightly elevated. Favour lighter, regularly-timed meals today and give yourself time between eating and sleeping.",
    },
    attention: {
      title: "Digestive signal stands out",
      tip: "Digestive markers are outside the reference range. If discomfort accompanies this, a clinician can help interpret it properly.",
    },
  },
};
