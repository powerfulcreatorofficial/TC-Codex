import { cn } from "@/lib/cn";

export type ConnectionState = "connected" | "connecting" | "degraded" | "disconnected" | "unknown";

const config: Record<ConnectionState, { color: string; label: string; ring: string }> = {
  connected: {
    color: "bg-success",
    label: "Connected",
    ring: "shadow-[0_0_0_3px_rgb(74_222_128/0.18)]",
  },
  connecting: {
    color: "bg-warning",
    label: "Connecting",
    ring: "shadow-[0_0_0_3px_rgb(251_191_36/0.18)]",
  },
  degraded: {
    color: "bg-warning",
    label: "Degraded",
    ring: "shadow-[0_0_0_3px_rgb(251_191_36/0.18)]",
  },
  disconnected: {
    color: "bg-error",
    label: "Disconnected",
    ring: "shadow-[0_0_0_3px_rgb(255_107_107/0.18)]",
  },
  unknown: { color: "bg-text-muted", label: "Unknown", ring: "" },
};

export interface ConnectionIndicatorProps {
  /** Human label for what is connected, e.g. "Orchestrator" or "Workspace Daemon". */
  name: string;
  state: ConnectionState;
  className?: string;
}

export function ConnectionIndicator({ name, state, className }: ConnectionIndicatorProps) {
  const cfg = config[state];
  const live = state === "connected";
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <span
        className={cn("h-2 w-2 rounded-full", cfg.color, live && "animate-pulse", cfg.ring)}
        aria-hidden="true"
      />
      <span className="text-xs font-medium text-text-secondary">
        <span className="text-text">{name}</span>
        <span className="mx-1.5 text-text-muted">·</span>
        {cfg.label}
      </span>
    </div>
  );
}
