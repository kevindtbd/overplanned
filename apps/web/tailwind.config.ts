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
        ink: {
          100: "var(--ink-100)",
          200: "var(--ink-200)",
          300: "var(--ink-300)",
          400: "var(--ink-400)",
          500: "var(--ink-500)",
          600: "var(--ink-600)",
          700: "var(--ink-700)",
          800: "var(--ink-800)",
          900: "var(--ink-900)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          light: "var(--accent-light)",
          muted: "var(--accent-muted)",
          fg: "var(--accent-fg)",
        },
        gold: { DEFAULT: "var(--gold)", light: "var(--gold-light)" },
        success: { DEFAULT: "var(--success)", bg: "var(--success-bg)" },
        info: { DEFAULT: "var(--info)", bg: "var(--info-bg)" },
        warning: { DEFAULT: "var(--warning)", bg: "var(--warning-bg)" },
        error: { DEFAULT: "var(--error)", bg: "var(--error-bg)" },
      },
      backgroundColor: {
        base: "var(--bg-base)",
        surface: "var(--bg-surface)",
        raised: "var(--bg-raised)",
        overlay: "var(--bg-overlay)",
        input: "var(--bg-input)",
        stone: "var(--bg-stone)",
        warm: "var(--bg-warm)",
      },
      borderColor: {
        DEFAULT: "var(--ink-700)",
      },
      textColor: {
        primary: "var(--ink-100)",
        secondary: "var(--ink-400)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        card: "var(--shadow-card)",
        xl: "var(--shadow-xl)",
      },
      fontFamily: {
        sora: ["var(--font-sora)", "system-ui", "sans-serif"],
        "dm-mono": ["var(--font-dm-mono)", "monospace"],
        lora: ["var(--font-lora)", "Georgia", "serif"],
      },
      keyframes: {
        "slot-reveal": {
          "0%": { opacity: "0", transform: "translateY(12px) scale(0.97)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
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
