"use client";

import * as React from "react";
import { TopBar } from "./TopBar";
import { BottomNav } from "./BottomNav";
import { SideRail } from "./SideRail";
import { useConnection } from "@/lib/connection";
import { CommandPalette } from "@/components/CommandPalette";
import type { OrbState } from "@/components/signature/TCOrb";

/**
 * Responsive application shell.
 * - Mobile: top bar + main + bottom nav.
 * - Desktop: left rail + main (with left padding to clear the rail).
 */
export function AppShell({
  children,
  orbState,
}: {
  children: React.ReactNode;
  orbState?: OrbState;
}) {
  const connectionState = useConnection();
  return (
    <>
      <SideRail connectionState={connectionState} />
      <TopBar connectionState={connectionState} orbState={orbState} />
      {/* md:pl-24 clears the 80px left rail; mx-auto centers the content column. */}
      <main className="safe-top mx-auto w-full max-w-3xl px-4 pb-24 pt-4 md:max-w-4xl md:pb-12 md:pl-24 md:pr-8">
        {children}
      </main>
      <BottomNav />
      <CommandPalette />
    </>
  );
}
