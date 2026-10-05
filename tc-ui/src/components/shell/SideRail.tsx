"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, ListChecks, ShieldCheck, Activity, FolderKanban, ClipboardList } from "lucide-react";
import { cn } from "@/lib/cn";
import { useSession } from "@/lib/session";
import { TCOrb } from "@/components/signature/TCOrb";
import { ConnectionIndicator } from "@/components/signature/ConnectionIndicator";
import type { ConnectionState } from "@/lib/hooks/use-api";

const items = [
  { href: "/", label: "Command", icon: Home, match: (p: string) => p === "/" },
  {
    href: "/projects",
    label: "Projects",
    icon: FolderKanban,
    match: (p: string) => p.startsWith("/projects"),
  },
  {
    href: "/plans",
    label: "Plans",
    icon: ClipboardList,
    match: (p: string) => p.startsWith("/plans"),
  },
  {
    href: "/tasks",
    label: "Tasks",
    icon: ListChecks,
    match: (p: string) => p.startsWith("/tasks"),
  },
  {
    href: "/approvals",
    label: "Approvals",
    icon: ShieldCheck,
    match: (p: string) => p.startsWith("/approvals"),
  },
  {
    href: "/system",
    label: "System",
    icon: Activity,
    match: (p: string) => p.startsWith("/system"),
  },
];

/** Desktop left navigation rail. Collapses to bottom nav on mobile. */
export function SideRail({ connectionState }: { connectionState: ConnectionState }) {
  const pathname = usePathname() ?? "/";
  const { awaitingApprovals } = useSession();
  const count = awaitingApprovals.length;

  return (
    <aside className="hidden md:fixed md:inset-y-0 md:left-0 md:z-sticky md:flex md:w-20 md:flex-col md:items-center md:gap-6 md:border-r md:border-border md:bg-surface md:py-6">
      <Link href="/" aria-label="Engineering TC home" className="mb-2">
        <TCOrb state="idle" size={40} />
      </Link>
      <ul className="flex flex-1 flex-col items-center gap-2">
        {items.map(({ href, label, icon: Icon, match }) => {
          const active = match(pathname);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "tap-target relative flex h-12 w-12 flex-col items-center justify-center gap-0.5 rounded-lg transition duration-fast ease-spring",
                  active
                    ? "bg-soft-green text-emerald"
                    : "text-text-muted hover:bg-surface-2 hover:text-text",
                )}
              >
                <span className="relative">
                  <Icon className="h-5 w-5" aria-hidden="true" />
                  {href === "/approvals" && count > 0 ? (
                    <span
                      className="absolute -right-2 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-warning px-1 text-[9px] font-semibold text-white"
                      aria-label={`${count} pending approvals`}
                    >
                      {count}
                    </span>
                  ) : null}
                </span>
                <span className="text-[9px] font-medium">{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
      <ConnectionIndicator name="Orchestrator" state={connectionState} />
    </aside>
  );
}
