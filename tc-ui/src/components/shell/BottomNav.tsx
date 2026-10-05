"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, ListChecks, ShieldCheck, Activity, FolderKanban, ClipboardList } from "lucide-react";
import { cn } from "@/lib/cn";
import { useSession } from "@/lib/session";

const items = [
  { href: "/", label: "Home", icon: Home, match: (p: string) => p === "/" },
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

/** Mobile bottom navigation. 44px touch targets, safe-area aware. */
export function BottomNav() {
  const pathname = usePathname() ?? "/";
  const { awaitingApprovals } = useSession();
  const count = awaitingApprovals.length;

  return (
    <nav
      aria-label="Primary"
      className="safe-bottom fixed inset-x-0 bottom-0 z-sticky border-t border-border bg-surface/95 backdrop-blur"
    >
      <ul className="mx-auto flex max-w-3xl items-stretch justify-around">
        {items.map(({ href, label, icon: Icon, match }) => {
          const active = match(pathname);
          return (
            <li key={href} className="flex-1">
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "tap-target relative flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition duration-fast ease-spring",
                  active ? "text-emerald" : "text-text-muted hover:text-text",
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
                <span>{label}</span>
                {active ? (
                  <span
                    className="absolute top-0 h-0.5 w-8 rounded-full bg-tc"
                    aria-hidden="true"
                  />
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
