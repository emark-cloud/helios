import type { Config } from "tailwindcss";

/**
 * Tailwind config mirrors src/styles/tokens.css.
 * If a token is missing here, also add it there. Single source of truth lives in CSS.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          base: "var(--surface-base)",
          1: "var(--surface-1)",
          panel: "var(--surface-panel)",
          elev: "var(--surface-elev)",
          hover: "var(--surface-hover)",
          line: "var(--surface-line)",
          "line-strong": "var(--surface-line-strong)",
        },
        fg: {
          DEFAULT: "var(--fg-primary)",
          primary: "var(--fg-primary)",
          secondary: "var(--fg-secondary)",
          muted: "var(--fg-muted)",
          disabled: "var(--fg-disabled)",
        },
        amber: {
          DEFAULT: "var(--accent-amber)",
          bright: "var(--accent-amber-bright)",
          dim: "var(--accent-amber-dim)",
          glow: "var(--accent-amber-glow)",
        },
        signal: {
          positive: "var(--signal-positive)",
          "positive-strong": "var(--signal-positive-strong)",
          "positive-dim": "var(--signal-positive-dim)",
          negative: "var(--signal-negative)",
          "negative-strong": "var(--signal-negative-strong)",
          "negative-dim": "var(--signal-negative-dim)",
        },
        chain: {
          kite: "var(--chain-kite)",
          base: "var(--chain-base)",
          arbitrum: "var(--chain-arbitrum)",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
        display: ["var(--font-display)"],
      },
      fontFeatureSettings: {
        numeric: 'var(--font-numeric-features)',
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
      },
      transitionDuration: {
        tick: "var(--tick-step)",
        segment: "var(--tick-segment)",
        cascade: "var(--tick-cascade)",
      },
    },
  },
  plugins: [],
};

export default config;
