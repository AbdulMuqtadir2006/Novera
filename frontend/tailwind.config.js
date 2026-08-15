/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#080919", // exact match to the logo's background navy
        signal: "#28CFE0", // cyan — primary accent (from the logo)
        iris: "#B24BD6", // purple — mid of the brand gradient
        vital: "#EC61E8", // magenta/pink — CTAs & highlights (from the logo)
        mist: "#EFEAFB", // light lavender page background
        paper: "#FBF9FE", // card/surface tone on light pages
        depth: "#241A44", // deep indigo text on light pages
        status: {
          good: "#3DDC97",
          watch: "#F2A93E",
          attention: "#FF5D5D",
        },
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', "system-ui", "sans-serif"],
        body: ['"Hanken Grotesk"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
        arabic: ['"Cairo"', "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 40px -8px rgba(40, 207, 224, 0.5)",
        "glow-sm": "0 0 24px -6px rgba(40, 207, 224, 0.4)",
        "glow-magenta": "0 0 40px -8px rgba(236, 97, 232, 0.5)",
        card: "0 10px 40px -20px rgba(36, 26, 68, 0.35)",
        lift: "0 20px 50px -24px rgba(36, 26, 68, 0.45)",
      },
      keyframes: {
        "pulse-ring": {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "70%": { transform: "scale(1.6)", opacity: "0" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-12px)" },
        },
        "drift-a": {
          "0%, 100%": { transform: "translate(0px, 0px) scale(1)" },
          "50%": { transform: "translate(40px, -30px) scale(1.1)" },
        },
        "drift-b": {
          "0%, 100%": { transform: "translate(0px, 0px) scale(1)" },
          "50%": { transform: "translate(-50px, 40px) scale(1.15)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "blink-caret": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
      },
      animation: {
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        float: "float 6s ease-in-out infinite",
        "drift-a": "drift-a 18s ease-in-out infinite",
        "drift-b": "drift-b 22s ease-in-out infinite",
        shimmer: "shimmer 1.8s infinite",
        "blink-caret": "blink-caret 1s step-end infinite",
      },
      transitionTimingFunction: {
        expo: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};
