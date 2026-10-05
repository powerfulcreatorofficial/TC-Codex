"use client";

import { useReducedMotion } from "framer-motion";
import { cn } from "@/lib/cn";
import { orbColors } from "@/design/tokens";

export type OrbState = "idle" | "thinking" | "executing" | "waiting" | "success" | "error";

export interface TCOrbProps {
  state?: OrbState;
  /** Diameter in px. Responsive via className where needed. */
  size?: number;
  className?: string;
  label?: string;
}

/**
 * Engineering TC Orb — the signature visual identity.
 *
 * Pure SVG + CSS. No WebGL / Three.js. Built to remain lightweight on mid-range
 * mobile devices. Decorative motion is fully suppressed under
 * prefers-reduced-motion (states still change instantly).
 *
 * States: idle (breathing), thinking (rotating internal structures),
 * executing (directional energy), waiting (amber/green restrained pulse),
 * success (brief energetic confirmation), error (restrained red).
 */
export function TCOrb({ state = "idle", size = 120, className, label }: TCOrbProps) {
  const reduce = useReducedMotion();
  const colors = orbColors[state];

  // Animations are applied as classes; under reduced motion the global CSS
  // rule forces near-zero durations, so state changes remain instant.
  const ringRotate = state === "thinking" || state === "executing";
  const ringRotateRev = state === "thinking";
  const breathe = state === "idle" || state === "success" || state === "waiting";

  return (
    <span
      className={cn("relative inline-flex items-center justify-center", className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={label ?? `TC Orb ${state}`}
    >
      {/* Outer ambient glow — restrained, identity only */}
      <span
        className="absolute inset-0 rounded-full blur-2xl"
        style={{ background: colors.glow, opacity: reduce ? 0.4 : 0.7 }}
        aria-hidden="true"
      />
      <svg viewBox="0 0 120 120" className="relative h-full w-full" aria-hidden="true">
        {/* gradient reserved for this small identity element only */}
        <defs>
          <radialGradient id="tc-orb-core" cx="50%" cy="45%" r="60%">
            <stop offset="0%" stopColor={colors.ring} />
            <stop offset="55%" stopColor={colors.core} />
            <stop offset="100%" stopColor={colors.core} stopOpacity={0.85} />
          </radialGradient>
          <linearGradient id="tc-orb-ring" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={colors.ring} />
            <stop offset="100%" stopColor={colors.core} />
          </linearGradient>
        </defs>

        {/* Outer ring */}
        <circle
          cx="60"
          cy="60"
          r="54"
          fill="none"
          stroke="url(#tc-orb-ring)"
          strokeWidth="1.5"
          strokeOpacity={0.45}
          className={cn(ringRotate && !reduce && "animate-orb-spin")}
          strokeDasharray="4 8"
        />
        {/* Middle structure — rotates counter on thinking */}
        <g
          className={cn(ringRotateRev && !reduce && "animate-orb-spin-rev")}
          style={{ transformOrigin: "60px 60px" }}
        >
          <circle
            cx="60"
            cy="60"
            r="42"
            fill="none"
            stroke={colors.ring}
            strokeWidth="1"
            strokeOpacity={0.3}
          />
          <path d="M60 18 L66 54 L60 60 L54 54 Z" fill={colors.core} opacity={0.5} />
          <path d="M102 60 L66 66 L60 60 L66 54 Z" fill={colors.core} opacity={0.35} />
          <path d="M60 102 L54 66 L60 60 L66 66 Z" fill={colors.ring} opacity={0.4} />
          <path d="M18 60 L54 54 L60 60 L54 66 Z" fill={colors.core} opacity={0.3} />
        </g>
        {/* Core */}
        <circle
          cx="60"
          cy="60"
          r="26"
          fill="url(#tc-orb-core)"
          className={cn(breathe && !reduce && "animate-orb-breathe")}
          style={{ transformOrigin: "60px 60px" }}
        />
        {/* Inner aperture */}
        <circle cx="60" cy="60" r="9" fill="rgb(var(--c-bg))" opacity={0.55} />
        <circle
          cx="60"
          cy="60"
          r="4.5"
          fill={colors.core}
          className={cn(state === "executing" && !reduce && "animate-orb-breathe")}
          style={{ transformOrigin: "60px 60px" }}
        />
      </svg>
    </span>
  );
}
