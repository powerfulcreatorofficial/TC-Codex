import type { Config } from "tailwindcss";

/**
 * Tailwind config. Colors are mapped from the CSS design tokens defined in
 * src/app/globals.css so the green/mint/teal identity is the single source of
 * truth and works with both Tailwind utilities and raw CSS variables.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Identity
        tc: "rgb(var(--c-tc) / <alpha-value>)",
        emerald: "rgb(var(--c-emerald) / <alpha-value>)",
        mint: "rgb(var(--c-mint) / <alpha-value>)",
        teal: "rgb(var(--c-teal) / <alpha-value>)",
        lime: "rgb(var(--c-lime) / <alpha-value>)",
        // Semantic
        success: "rgb(var(--c-success) / <alpha-value>)",
        warning: "rgb(var(--c-warning) / <alpha-value>)",
        error: "rgb(var(--c-error) / <alpha-value>)",
        // Surfaces / text
        bg: "rgb(var(--c-bg) / <alpha-value>)",
        surface: "rgb(var(--c-surface) / <alpha-value>)",
        "surface-2": "rgb(var(--c-surface-2) / <alpha-value>)",
        text: "rgb(var(--c-text) / <alpha-value>)",
        "text-secondary": "rgb(var(--c-text-secondary) / <alpha-value>)",
        "text-muted": "rgb(var(--c-text-muted) / <alpha-value>)",
        border: "rgb(var(--c-border) / <alpha-value>)",
        "border-strong": "rgb(var(--c-border-strong) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        sm: "var(--r-sm)",
        DEFAULT: "var(--r-md)",
        md: "var(--r-md)",
        lg: "var(--r-lg)",
        xl: "var(--r-xl)",
        "2xl": "var(--r-2xl)",
        pill: "var(--r-pill)",
      },
      boxShadow: {
        xs: "var(--sh-xs)",
        sm: "var(--sh-sm)",
        md: "var(--sh-md)",
        lg: "var(--sh-lg)",
        glow: "var(--sh-glow)",
      },
      spacing: {
        "0.5": "var(--s-0-5)",
        "1.5": "var(--s-1-5)",
        "18": "var(--s-18)",
        "22": "var(--s-22)",
      },
      transitionTimingFunction: {
        spring: "var(--ease-spring)",
        smooth: "var(--ease-smooth)",
      },
      transitionDuration: {
        micro: "var(--d-micro)",
        fast: "var(--d-fast)",
        base: "var(--d-base)",
        slow: "var(--d-slow)",
      },
      zIndex: {
        base: "var(--z-base)",
        sticky: "var(--z-sticky)",
        dropdown: "var(--z-dropdown)",
        overlay: "var(--z-overlay)",
        modal: "var(--z-modal)",
        toast: "var(--z-toast)",
      },
      keyframes: {
        "orb-breathe": {
          "0%, 100%": { transform: "scale(1)", opacity: "0.85" },
          "50%": { transform: "scale(1.04)", opacity: "1" },
        },
        "orb-spin": {
          to: { transform: "rotate(360deg)" },
        },
        "orb-spin-rev": {
          to: { transform: "rotate(-360deg)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "orb-breathe": "orb-breathe 4s var(--ease-spring) infinite",
        "orb-spin": "orb-spin 6s linear infinite",
        "orb-spin-rev": "orb-spin-rev 9s linear infinite",
        "fade-in": "fade-in var(--d-base) var(--ease-smooth) both",
        "slide-up": "slide-up var(--d-base) var(--ease-smooth) both",
      },
    },
  },
  plugins: [],
};

export default config;
