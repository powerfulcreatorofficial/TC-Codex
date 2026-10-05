import * as React from "react";
import { cn } from "@/lib/cn";

type Tone = "neutral" | "green" | "teal" | "warning" | "error" | "success";

const toneClasses: Record<Tone, string> = {
  neutral: "bg-surface-2 text-text-secondary border-border",
  green: "bg-soft-green text-emerald border-tc/20",
  teal: "bg-teal/10 text-teal border-teal/20",
  warning: "bg-warning/10 text-warning border-warning/20",
  error: "bg-error/10 text-error border-error/20",
  success: "bg-success/10 text-success border-success/20",
};

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

export function Badge({ className, tone = "neutral", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-pill border px-2.5 py-0.5 text-xs font-medium",
        toneClasses[tone],
        className,
      )}
      {...props}
    />
  );
}
