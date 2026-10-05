import * as React from "react";
import { cn } from "@/lib/cn";

export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
}

/** Accessible square icon button — enforces an accessible name + 44px target. */
export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { className, label, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      aria-label={label}
      title={label}
      className={cn(
        "tap-target inline-flex h-11 w-11 items-center justify-center rounded-lg text-text-secondary",
        "transition duration-fast ease-spring hover:bg-surface-2 hover:text-text focus-visible:shadow-glow",
        "disabled:pointer-events-none disabled:opacity-50",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
});
