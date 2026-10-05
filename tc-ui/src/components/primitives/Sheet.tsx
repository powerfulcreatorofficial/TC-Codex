"use client";

import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";
import { IconButton } from "./IconButton";

export interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  side?: "right" | "bottom";
  children?: React.ReactNode;
  className?: string;
}

/** Accessible side/bottom sheet built on Radix Dialog. Mobile-first. */
export function Sheet({
  open,
  onOpenChange,
  title,
  side = "right",
  children,
  className,
}: SheetProps) {
  const sideClasses =
    side === "right"
      ? "inset-y-0 right-0 h-full w-[calc(100vw-1.5rem)] max-w-md rounded-l-xl"
      : "inset-x-0 bottom-0 w-full max-h-[85vh] rounded-t-xl";
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-overlay bg-text/30 backdrop-blur-[2px] data-[state=open]:animate-fade-in" />
        <Dialog.Content
          className={cn(
            "fixed z-modal border border-border bg-surface p-5 shadow-lg focus:outline-none",
            "data-[state=open]:animate-slide-up",
            sideClasses,
            className,
          )}
        >
          {title ? (
            <Dialog.Title className="mb-4 pr-8 text-base font-semibold tracking-tight text-text">
              {title}
            </Dialog.Title>
          ) : null}
          <div className="scrollbar-thin overflow-y-auto">{children}</div>
          <Dialog.Close asChild>
            <IconButton label="Close sheet" className="absolute right-3 top-3 h-9 w-9">
              <X className="h-5 w-5" aria-hidden="true" />
            </IconButton>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
