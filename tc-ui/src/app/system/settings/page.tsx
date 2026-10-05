"use client";

import * as React from "react";
import Link from "next/link";
import { Check, Monitor, Moon, Sun } from "lucide-react";
import { AppShell } from "@/components/shell/AppShell";
import { Card, CardBody, CardHeader, Button } from "@/components/primitives";
import { cn } from "@/lib/cn";
import { useTheme } from "@/lib/theme";

function useLocalStorage(key: string, initial: string) {
  const [val, setVal] = React.useState<string>(initial);
  React.useEffect(() => {
    const stored = window.localStorage.getItem(key);
    if (stored !== null) setVal(stored);
  }, [key]);
  const update = React.useCallback((v: string) => {
    setVal(v);
    try { window.localStorage.setItem(key, v); } catch { /* ignore */ }
  }, [key]);
  return [val, update] as const;
}

function Toggle({ on, onToggle, label, id }: { on: boolean; onToggle: () => void; label: string; id: string }) {
  return (
    <button id={id} type="button" role="switch" aria-checked={on} onClick={onToggle} aria-label={label} className={cn("tap-target relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border border-border transition", on ? "bg-tc" : "bg-surface-2")}>
      <span className={cn("inline-block h-4 w-4 rounded-full bg-white shadow-sm transition", on ? "translate-x-6" : "translate-x-1")} />
    </button>
  );
}

export default function SettingsPage() {
  const { theme, setTheme, resolved } = useTheme();
  const [reduceMotion, setReduceMotion] = useLocalStorage("tc-reduce-motion", "false");
  const [compact, setCompact] = useLocalStorage("tc-compact", "false");

  const modes = [
    { id: "light" as const, label: "Light", icon: Sun },
    { id: "dark" as const, label: "Dark", icon: Moon },
    { id: "system" as const, label: "System", icon: Monitor },
  ];

  return (
    <AppShell>
      <Link href="/system"><Button variant="ghost" size="sm">← System</Button></Link>
      <div className="mt-3 max-w-2xl">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald">Control preferences</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight text-text">Settings</h1>
        <p className="mt-2 text-sm leading-6 text-text-secondary">Tune the TC command center without changing the secure execution architecture.</p>
      </div>

      <Card className="mt-6 max-w-3xl overflow-hidden">
        <CardHeader>
          <h2 className="text-sm font-semibold text-text">Appearance</h2>
          <p className="mt-1 text-xs text-text-muted">TC keeps the green / mint / teal identity in every mode.</p>
        </CardHeader>
        <CardBody className="space-y-5 pt-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-text-muted">Theme</p>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {modes.map(({ id, label, icon: Icon }) => (
                <button key={id} type="button" onClick={() => setTheme(id)} aria-pressed={theme === id} className={cn("flex min-h-14 items-center justify-center gap-2 rounded-xl border px-3 text-xs font-medium transition", theme === id ? "border-tc bg-soft-green text-emerald" : "border-border bg-surface hover:bg-surface-2 text-text-secondary")}>
                  <Icon className="h-4 w-4" />
                  {label}
                  {theme === id ? <Check className="h-3.5 w-3.5" /> : null}
                </button>
              ))}
            </div>
            <p className="mt-2 font-mono text-[10px] text-text-muted">Resolved theme: {resolved}</p>
          </div>
          <div className="flex items-center justify-between gap-4 border-t border-border pt-4">
            <div><p className="text-sm font-medium text-text">Reduce motion</p><p className="text-xs text-text-muted">Minimize decorative movement.</p></div>
            <Toggle id="reduce-motion" label="Reduce motion" on={reduceMotion === "true"} onToggle={() => setReduceMotion(reduceMotion === "true" ? "false" : "true")} />
          </div>
          <div className="flex items-center justify-between gap-4 border-t border-border pt-4">
            <div><p className="text-sm font-medium text-text">Compact density</p><p className="text-xs text-text-muted">Use tighter spacing for dense engineering sessions.</p></div>
            <Toggle id="compact" label="Compact density" on={compact === "true"} onToggle={() => setCompact(compact === "true" ? "false" : "true")} />
          </div>
        </CardBody>
      </Card>

      <Card className="mt-4 max-w-3xl">
        <CardHeader>
          <h2 className="text-sm font-semibold text-text">Execution & security</h2>
        </CardHeader>
        <CardBody className="pt-3">
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              ["Approval policy", "Owner-gated for mutating tools"],
              ["Workspace boundary", "Rust daemon / confined root"],
              ["Owner token", "Memory-only browser session"],
              ["Secret handling", "Never rendered in UI"],
            ].map(([label, value]) => <div key={label} className="rounded-xl border border-border bg-surface-2/50 px-3 py-3"><p className="text-xs font-medium text-text">{label}</p><p className="mt-1 font-mono text-[10px] text-text-muted">{value}</p></div>)}
          </div>
        </CardBody>
      </Card>
    </AppShell>
  );
}
