"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Command, Search, Home, ListChecks, ShieldCheck, Settings, Activity, Plus } from "lucide-react";
import { Modal } from "@/components/primitives/Modal";
import { cn } from "@/lib/cn";

const actions = [
  { id: "home", label: "Command Center", hint: "Open TC home", icon: Home, href: "/" },
  { id: "new", label: "New engineering task", hint: "Start a fresh task", icon: Plus, href: "/" },
  { id: "tasks", label: "Tasks", hint: "Review task history", icon: ListChecks, href: "/tasks" },
  { id: "approvals", label: "Approvals", hint: "Review waiting actions", icon: ShieldCheck, href: "/approvals" },
  { id: "system", label: "System", hint: "Check service health", icon: Activity, href: "/system" },
  { id: "settings", label: "Settings", hint: "Configure TC", icon: Settings, href: "/system/settings" },
];

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [active, setActive] = React.useState(0);

  React.useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      if ((event.metaKey || event.ctrlKey) && key === "k") {
        event.preventDefault();
        setOpen(true);
      }
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? actions.filter((a) => `${a.label} ${a.hint}`.toLowerCase().includes(q)) : actions;
  }, [query]);

  React.useEffect(() => setActive(0), [query]);

  const choose = (href: string) => {
    setOpen(false);
    setQuery("");
    router.push(href);
  };

  return (
    <Modal open={open} onOpenChange={setOpen} title="Command palette" className="max-w-xl p-0">
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-center gap-2 rounded-lg border border-border bg-surface-2 px-3">
          <Search className="h-4 w-4 text-text-muted" aria-hidden="true" />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActive((i) => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                setActive((i) => Math.max(i - 1, 0));
              }
              if (event.key === "Enter" && filtered[active]) choose(filtered[active].href);
            }}
            placeholder="Jump to a TC surface…"
            className="h-11 min-w-0 flex-1 bg-transparent text-sm text-text outline-none placeholder:text-text-muted"
            aria-label="Search TC commands"
          />
          <span className="hidden items-center gap-1 rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[10px] text-text-muted sm:flex">
            <Command className="h-3 w-3" />K
          </span>
        </div>
      </div>
      <div className="p-2">
        {filtered.length === 0 ? (
          <div className="px-3 py-10 text-center text-sm text-text-muted">No matching TC commands.</div>
        ) : (
          filtered.map((item, index) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(item.href)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left transition",
                  index === active ? "bg-soft-green" : "hover:bg-surface-2",
                )}
              >
                <span className="grid h-9 w-9 place-items-center rounded-lg border border-border bg-surface">
                  <Icon className={cn("h-4 w-4", index === active ? "text-emerald" : "text-text-secondary")} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-text">{item.label}</span>
                  <span className="block text-xs text-text-muted">{item.hint}</span>
                </span>
                <span className="text-[10px] text-text-muted">↵</span>
              </button>
            );
          })
        )}
      </div>
    </Modal>
  );
}
