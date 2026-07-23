import {defineConfig} from "vite";
import react, {reactCompilerPreset} from "@vitejs/plugin-react";
import babel from "@rolldown/plugin-babel";
import {viteSingleFile} from "vite-plugin-singlefile";

// https://vite.dev/config/
export default defineConfig(({mode}) => ({
  plugins: [
    react(),
    babel({presets: [reactCompilerPreset()]}),
    ...(mode === "singlefile" ? [viteSingleFile()] : []),
  ],
  cacheDir: process.env.VITE_CACHE_DIR ?? "node_modules/.vite",
  build: {
    outDir: process.env.VITE_OUT_DIR ?? "dist",
    emptyOutDir: true,
    cssCodeSplit: mode !== "singlefile",
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: "binary", // Will emit as dist/assets/game-binary-[hash].js
              test: /binary\.js/, // Matches your compiled game binary path or file name
            },
            {
              name: "simulator",
              test: /---simulator\.html/,
            },
          ],
        },
      },
    },
  },
}));
