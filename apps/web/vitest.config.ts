import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    root: ".",
    include: ["__tests__/**/*.test.{ts,tsx}"],
    exclude: [
      "__tests__/e2e/**",
      "**/tracks/**",
      "**/.claude/**",
    ],
    globals: true,
    coverage: {
      provider: "v8",
      include: ["app/**", "lib/**", "components/**"],
      exclude: ["**/*.d.ts", "app/**/layout.tsx"],
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./"),
      "@/app": path.resolve(__dirname, "./app"),
      "@/lib": path.resolve(__dirname, "./lib"),
      "@/components": path.resolve(__dirname, "./components"),
      "server-only": path.resolve(__dirname, "./__mocks__/server-only.ts"),
    },
  },
});
