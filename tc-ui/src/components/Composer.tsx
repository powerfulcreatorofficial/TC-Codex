"use client";

import * as React from "react";
import { ArrowUp, Paperclip, Sparkles } from "lucide-react";
import { Textarea } from "@/components/primitives/Input";
import { IconButton } from "@/components/primitives/IconButton";
import { Spinner } from "@/components/primitives/Spinner";

export interface ComposerProps {
  busy?: boolean;
  onSubmit: (prompt: string) => void | Promise<void>;
  placeholder?: string;
}

export function Composer({ busy, onSubmit, placeholder }: ComposerProps) {
  const [value, setValue] = React.useState("");
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  const submit = React.useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    void onSubmit(trimmed);
    setValue("");
    textareaRef.current?.focus();
  }, [value, busy, onSubmit]);

  React.useEffect(() => {
    const handler = (event: Event) => {
      const prompt = (event as CustomEvent<string>).detail;
      if (typeof prompt === "string") {
        setValue(prompt);
        requestAnimationFrame(() => textareaRef.current?.focus());
      }
    };
    window.addEventListener("tc:prefill", handler);
    return () => window.removeEventListener("tc:prefill", handler);
  }, []);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="rounded-[22px] border border-border bg-surface shadow-sm transition duration-fast ease-spring focus-within:border-tc/40 focus-within:shadow-glow">
      <div className="flex items-end gap-2 p-2.5">
        <IconButton label="Add attachment" disabled className="hidden h-11 w-11 shrink-0 sm:flex">
          <Paperclip className="h-4 w-4" aria-hidden="true" />
        </IconButton>
        <div className="min-w-0 flex-1">
          <Textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={busy}
            aria-label="Engineering request"
            placeholder={placeholder ?? "Tell TC what you want to build…"}
            rows={2}
            className="min-h-[54px] resize-none border-0 bg-transparent px-2 py-1.5 text-sm shadow-none focus-visible:border-transparent focus-visible:shadow-none"
          />
        </div>
        <IconButton
          label={busy ? "TC is working" : "Send engineering request"}
          onClick={submit}
          disabled={busy || value.trim().length === 0}
          className="h-11 w-11 shrink-0 bg-tc text-white hover:brightness-105 disabled:opacity-40"
        >
          {busy ? <Spinner size="sm" className="text-white" /> : <ArrowUp className="h-5 w-5" aria-hidden="true" />}
        </IconButton>
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-border px-4 py-2.5 text-[10px] text-text-muted">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-tc" />
          <span>TC can plan, execute, test, repair, and verify.</span>
        </div>
        <span className="hidden font-mono sm:inline">Enter ↵ · Shift+Enter</span>
      </div>
    </div>
  );
}
