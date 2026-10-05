"use client";

import { TCOrb } from "@/components/signature/TCOrb";
import { ConnectionIndicator } from "@/components/signature/ConnectionIndicator";
import type { ConnectionState } from "@/lib/hooks/use-api";
import type { OrbState } from "@/components/signature/TCOrb";

/** Mobile top bar: TC identity orb + connection indicator. */
export function TopBar({
  connectionState,
  orbState = "idle",
}: {
  connectionState: ConnectionState;
  orbState?: OrbState;
}) {
  return (
    <header className="safe-top sticky top-0 z-sticky flex items-center justify-between border-b border-border bg-surface/90 px-4 py-3 backdrop-blur md:hidden">
      <div className="flex items-center gap-2.5">
        <TCOrb state={orbState} size={32} />
        <div className="leading-tight">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-emerald">
            Engineering TC
          </p>
        </div>
      </div>
      <ConnectionIndicator name="Live" state={connectionState} />
    </header>
  );
}
