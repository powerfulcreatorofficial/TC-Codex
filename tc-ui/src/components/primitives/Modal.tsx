"use client";

import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";
import { IconButton } from "./IconButton";

export interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  description?: string;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

/** Accessible centered modal dialog built on Radix Dialog. */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  className,
}: ModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-overlay bg-text/30 backdrop-blur-[2px] data-[state=open]:animate-fade-in" />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-modal w-[calc(100vw-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2",
            "rounded-xl border border-border bg-surface p-6 shadow-lg focus:outline-none",
            "data-[state=open]:animate-slide-up",
            className,
          )}
        >
          {title ? (
            <Dialog.Title className="text-lg font-semibold tracking-tight text-text">
              {title}
            </Dialog.Title>
          ) : null}
          {description ? (
            <Dialog.Description className="mt-1.5 text-sm text-text-secondary">
              {description}
            </Dialog.Description>
          ) : null}
          <div className="mt-4">{children}</div>
          {footer ? <div className="mt-6 flex justify-end gap-3">{footer}</div> : null}
          <Dialog.Close asChild>
            <IconButton label="Close dialog" className="absolute right-3 top-3 h-9 w-9">
              <X className="h-5 w-5" aria-hidden="true" />
            </IconButton>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
