/**
 * Design tokens mirrored for TypeScript consumers (e.g. Framer Motion variants,
 * inline SVG). The CSS variables in globals.css remain the single source of
 * truth for styling; these are for values the JS layer needs directly.
 */

export const motion = {
  duration: {
    micro: 0.15,
    fast: 0.22,
    base: 0.3,
    slow: 0.42,
  },
  ease: {
    spring: [0.22, 1, 0.36, 1] as const,
    smooth: [0.4, 0, 0.2, 1] as const,
  },
} as const;

export const radii = {
  sm: "var(--r-sm)",
  md: "var(--r-md)",
  lg: "var(--r-lg)",
  xl: "var(--r-xl)",
  "2xl": "var(--r-2xl)",
  pill: "var(--r-pill)",
} as const;

/** Resolves a CSS variable to a value usable in inline styles (mostly for SVG). */
export const token = (name: string): string => `var(${name})`;

export const orbColors = {
  idle: {
    core: "rgb(var(--c-tc))",
    ring: "rgb(var(--c-mint))",
    glow: "rgb(53 229 140 / 0.22)",
  },
  thinking: {
    core: "rgb(var(--c-teal))",
    ring: "rgb(var(--c-mint))",
    glow: "rgb(37 199 181 / 0.28)",
  },
  executing: {
    core: "rgb(var(--c-tc))",
    ring: "rgb(var(--c-emerald))",
    glow: "rgb(11 143 98 / 0.30)",
  },
  waiting: {
    core: "rgb(var(--c-warning))",
    ring: "rgb(var(--c-tc))",
    glow: "rgb(251 191 36 / 0.24)",
  },
  success: {
    core: "rgb(var(--c-success))",
    ring: "rgb(var(--c-mint))",
    glow: "rgb(74 222 128 / 0.30)",
  },
  error: {
    core: "rgb(var(--c-error))",
    ring: "rgb(var(--c-error))",
    glow: "rgb(255 107 107 / 0.22)",
  },
} as const;
