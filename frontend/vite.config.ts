import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("/node_modules/recharts/")) {
            return "charts";
          }
          if (id.includes("/node_modules/d3-")) return "d3";
          if (id.includes("/node_modules/lucide-react/")) {
            return "icons";
          }
          if (id.includes("/node_modules/react/") || id.includes("/node_modules/scheduler/")) {
            return "react-vendor";
          }
        },
      },
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
  },
});
