import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "favicon.png", "apple-touch-icon.png"],
      manifest: {
        name: "Novera",
        short_name: "Novera",
        description:
          "Novera — an agentic AI-driven saliva biosensor platform for non-invasive health screening.",
        theme_color: "#080919",
        background_color: "#080919",
        display: "standalone",
        start_url: "/",
        scope: "/",
        icons: [
          { src: "/pwa-192.png", sizes: "192x192", type: "image/png" },
          { src: "/pwa-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/pwa-maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // The 480 hero frame JPGs (desktop + mobile sets) are excluded —
        // precaching them would bloat install time and device storage;
        // they're small enough individually to just load over the network
        // as the hero scrubs, same as today.
        globPatterns: ["**/*.{js,css,html,svg,png,ico,woff2}"],
        globIgnores: ["frames/**", "frames-mobile/**"],
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
      },
    }),
  ],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          motion: ["framer-motion", "gsap"],
          charts: ["recharts"],
          // pdf (jspdf/html2canvas) deliberately NOT grouped here (2026-08-23):
          // an explicit manualChunks entry makes Vite treat it as an
          // always-needed vendor chunk and <link rel="modulepreload"> it in
          // index.html regardless of whether it's ever actually reached —
          // silently defeating Reports.jsx's dynamic import() of
          // generateReportPdf.js. Left to Vite's own automatic
          // dynamic-import-graph chunking instead, which correctly does NOT
          // preload something only reachable through a real dynamic import.
        },
      },
    },
  },
});
