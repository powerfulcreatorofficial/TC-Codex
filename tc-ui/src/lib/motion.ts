"use client";

import { useReducedMotion } from "framer-motion";
import { motion as m } from "framer-motion";
import type { Variants, Transition } from "framer-motion";
import { motion as tokens } from "@/design/tokens";

/** Shared motion presets. Decorative animation is disabled under reduced motion. */

export function useSpring(): boolean {
  return !useReducedMotion();
}

const springTransition: Transition = {
  type: "spring",
  stiffness: 320,
  damping: 30,
  mass: 0.8,
};

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: tokens.duration.base, ease: tokens.ease.smooth },
  },
};

export const springCard: Variants = {
  hidden: { opacity: 0, scale: 0.98 },
  visible: { opacity: 1, scale: 1, transition: springTransition },
};

export { springTransition };

/** Re-export framer-motion's `motion` for convenient, consistent usage. */
export { m };
