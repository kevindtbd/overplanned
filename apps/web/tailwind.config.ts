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
      keyframes: {
        "slot-reveal": {
          "0%": {
            opacity: "0",
            transform: "translateY(12px) scale(0.97)",
          },
          "100%": {
            opacity: "1",
            transform: "translateY(0) scale(1)",
          },
        },
      },
      animation: {
        "slot-reveal": "slot-reveal 0.5s ease-out forwards",
      },
    },
  },
  plugins: [],
};

export default config;
