import {defineConfig} from "vite";
import react, {reactCompilerPreset} from "@vitejs/plugin-react";
import babel from "@rolldown/plugin-babel";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), babel({presets: [reactCompilerPreset()]})],
  build: {
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
});
