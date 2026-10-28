import { defineConfig } from "vite";

const headers = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
};

const proxy = {
  "/api": "http://127.0.0.1:8787",
  "/eval": "http://127.0.0.1:8787",
  "/ort": "http://127.0.0.1:8787",
};

export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 5173,
    headers,
    proxy,
  },
  preview: {
    host: "127.0.0.1",
    port: 5173,
    headers,
    proxy,
  },
  worker: { format: "es" },
  optimizeDeps: {
    exclude: ["@huggingface/transformers"],
  },
});
