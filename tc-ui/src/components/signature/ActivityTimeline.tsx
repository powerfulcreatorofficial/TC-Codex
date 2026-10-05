import * as React from "react";
import { cn } from "@/lib/cn";
import { Card } from "../primitives/Card";

/**
 * Activity timeline. Items are generic so this component is reusable without
 * assuming a specific backend shape; callers map real `TaskEvent` rows into
 * `ActivityItem[]`.
 */
export interface ActivityItem {
  id: string | number;
  title: string;
  meta?: string;
  tone?: "neutral" | "green" | "teal" | "warning" | "error" | "success";
  icon?: React.ReactNode;
}

const toneDot: Record<NonNullable<ActivityItem["tone"]>, string> = {
  neutral: "bg-text-muted",
  green: "bg-tc",
  teal: "bg-teal",
  warning: "bg-warning",
  error: "bg-error",
  success: "bg-success",
};

export interface ActivityTimelineProps {
  items: ActivityItem[];
  /** Header shown above the list. */
  title?: string;
  /** Empty state content when there are no items. */
  empty?: React.ReactNode;
  className?: string;
}

export function ActivityTimeline({ items, title, empty, className }: ActivityTimelineProps) {
  return (
    <Card className={cn("p-5", className)}>
      {title ? <h3 className="text-sm font-semibold text-text">{title}</h3> : null}
      {items.length === 0 ? (
        <div className="py-8 text-center text-sm text-text-muted">{empty ?? "No activity yet"}</div>
      ) : (
        <ol className={cn("relative space-y-4", title && "mt-4")}>
          {items.map((item, i) => (
            <li key={item.id} className="relative flex gap-3 pl-1">
              {i < items.length - 1 ? (
                <span
                  className="absolute left-[7px] top-5 h-[calc(100%+0.25rem)] w-px bg-border"
                  aria-hidden="true"
                />
              ) : null}
              <span
                className={cn(
                  "relative z-base mt-1 h-3.5 w-3.5 shrink-0 rounded-full ring-4 ring-surface",
                  toneDot[item.tone ?? "neutral"],
                )}
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  {item.icon}
                  <p className="truncate text-sm font-medium text-text">{item.title}</p>
                </div>
                {item.meta ? <p className="mt-0.5 text-xs text-text-muted">{item.meta}</p> : null}
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
