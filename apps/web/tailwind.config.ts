import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        terracotta: {
          DEFAULT: "var(--color-terracotta)",
          50: "#FDF5F2",
          100: "#FAEAE4",
          200: "#F2CFC2",
          300: "#E8B09D",
          400: "#D68D73",
          500: "#C4694F",
          600: "#A8553D",
          700: "#8B4332",
          800: "#6E3528",
          900: "#52281E",
        },
        warm: {
          background: "var(--color-warm-background)",
          surface: "var(--color-warm-surface)",
          border: "var(--color-warm-border)",
          "text-primary": "var(--color-warm-text-primary)",
          "text-secondary": "var(--color-warm-text-secondary)",
        },
      },
      fontFamily: {
        sora: ["var(--font-sora)", "system-ui", "sans-serif"],
        "dm-mono": ["var(--font-dm-mono)", "monospace"],
        lora: ["var(--font-lora)", "Georgia", "serif"],
      },
      backgroundColor: {
        app: "var(--color-warm-background)",
        surface: "var(--color-warm-surface)",
      },
      borderColor: {
        warm: "var(--color-warm-border)",
      },
      textColor: {
        primary: "var(--color-warm-text-primary)",
        secondary: "var(--color-warm-text-secondary)",
      },
    },
  },
  plugins: [],
};

export default config;
