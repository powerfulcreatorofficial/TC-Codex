import * as React from "react";
import { cn } from "@/lib/cn";

const baseField =
  "w-full bg-surface text-text placeholder:text-text-muted border border-border-strong rounded-lg px-3.5 " +
  "transition duration-fast ease-spring focus-visible:outline-none focus-visible:border-tc focus-visible:shadow-glow " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        baseField,
        "tap-target h-11",
        invalid && "border-error focus-visible:border-error",
        className,
      )}
      {...props}
    />
  );
});

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, invalid, ...props },
  ref,
) {
  return (
    <textarea
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        baseField,
        "min-h-22 resize-y py-3 leading-relaxed",
        invalid && "border-error",
        className,
      )}
      {...props}
    />
  );
});
