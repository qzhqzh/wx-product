import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  build: {
    manifest: true,
    outDir: "static/dist",
    emptyOutDir: true,
    rollupOptions: {
      input: "frontend/main.js",
    },
  },
});
