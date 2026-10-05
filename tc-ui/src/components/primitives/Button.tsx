import * as React from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "subtle";
type Size = "sm" | "md" | "lg" | "icon";

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-tc text-white font-medium shadow-sm hover:brightness-105 active:brightness-95 focus-visible:shadow-glow",
  secondary:
    "bg-surface text-text border border-border-strong hover:bg-surface-2 active:bg-surface-2",
  ghost: "bg-transparent text-text-secondary hover:bg-surface-2 hover:text-text",
  danger: "bg-error text-white font-medium hover:brightness-105 active:brightness-95",
  subtle: "bg-soft-green text-emerald font-medium hover:brightness-100",
};

const sizeClasses: Record<Size, string> = {
  sm: "h-9 px-3 text-sm rounded-md",
  md: "h-11 px-4 text-sm rounded-lg tap-target",
  lg: "h-12 px-6 text-base rounded-lg tap-target",
  icon: "h-11 w-11 rounded-lg tap-target justify-center",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", size = "md", loading, children, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap transition duration-fast ease-spring",
        "disabled:pointer-events-none disabled:opacity-50",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    >
      {loading ? (
        <span
          className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
          aria-hidden="true"
        />
      ) : null}
      {children}
    </button>
  );
});
