import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["cjs", "esm", "iife"],
  globalName: "Cortex",
  dts: true,
  minify: true,
  sourcemap: true,
  clean: true,
  outDir: "dist",
  outExtension({ format }) {
    if (format === "iife") return { js: ".min.js" };
    if (format === "esm") return { js: ".mjs" };
    return { js: ".js" };
  },
});
