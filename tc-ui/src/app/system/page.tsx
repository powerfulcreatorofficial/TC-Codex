"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/shell/AppShell";
import { Card, CardBody, CardHeader, Button, Skeleton } from "@/components/primitives";
import { ConnectionIndicator } from "@/components/signature/ConnectionIndicator";
import { useHealth } from "@/lib/hooks/use-api";
import type { ConnectionState } from "@/lib/hooks/use-api";
import { formatTime } from "@/lib/format";
import { orchestrator } from "@/lib/api/orchestrator";

/**
 * System status dashboard.
 *
 * Renders ONLY what the real backend exposes via GET /health: an overall
 * status plus the daemon and database reachability. The Brain is not exposed
 * by /health, so it is shown as "unknown" (not inferred healthy). There are
 * no resource metrics endpoints, so metrics are reported unavailable rather
 * than fabricated.
 */

function toState(v: string | null | undefined): ConnectionState {
  if (v === "reachable") return "connected";
  if (v === "unreachable") return "disconnected";
  if (v === "unconfigured") return "unknown";
  return "unknown";
}

function StatusCard({
  title,
  name,
  state,
  loading,
  note,
}: {
  title: string;
  name: string;
  state: ConnectionState;
  loading: boolean;
  note?: string;
}) {
  return (
    <Card>
      <CardHeader>
        <h2 className="text-sm font-semibold text-text">{title}</h2>
      </CardHeader>
      <CardBody className="pt-3">
        {loading ? (
          <Skeleton className="h-5 w-40" />
        ) : (
          <ConnectionIndicator name={name} state={state} />
        )}
        {note ? <p className="mt-2 text-xs text-text-muted">{note}</p> : null}
      </CardBody>
    </Card>
  );
}

export default function SystemPage() {
  const { health, state, error } = useHealth(5000);
  const [lastUpdated, setLastUpdated] = React.useState<string | null>(null);
  const [retrying, setRetrying] = React.useState(false);
  const [brain, setBrain] = React.useState<Awaited<ReturnType<typeof orchestrator.brainStatus>> | null>(null);

  React.useEffect(() => {
    let alive = true;
    orchestrator.brainStatus().then((value) => { if (alive) setBrain(value); }).catch(() => { if (alive) setBrain(null); });
    return () => { alive = false; };
  }, [health]);

  React.useEffect(() => {
    if (health) setLastUpdated(new Date().toISOString());
  }, [health]);

  const loading = !health && !error;

  return (
    <AppShell>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight text-text">System</h1>
        <Button
          variant="ghost"
          size="sm"
          loading={retrying}
          onClick={async () => {
            setRetrying(true);
            try {
              await import("@/lib/api/orchestrator").then((m) => m.orchestrator.health());
            } catch {
              /* useHealth will reflect state */
            }
            setRetrying(false);
          }}
        >
          Retry
        </Button>
      </div>
      <p className="mt-1 text-xs text-text-muted">Live status from the orchestrator.</p>

      {error ? (
        <p className="mt-2 rounded-md bg-error/10 px-3 py-2 text-xs text-error" role="alert">
          Unable to load system status. Retry.
        </p>
      ) : null}

      <div className="mt-4 space-y-3">
        <StatusCard
          title="Orchestrator"
          name="Health"
          state={state}
          loading={loading}
          note={health ? `Overall: ${health.status}` : undefined}
        />
        <StatusCard
          title="Workspace daemon"
          name="Daemon"
          state={health ? toState(health.daemon) : "unknown"}
          loading={loading}
        />
        <StatusCard
          title="PostgreSQL"
          name="Database"
          state={health ? toState(health.database) : "unknown"}
          loading={loading}
        />
        <StatusCard
          title="Brain"
          name="Brain"
          state={brain ? (brain.higher_enabled && brain.higher_configured ? "connected" : "unknown") : "unknown"}
          loading={!brain && !error}
          note={brain ? `Primary: ${brain.primary_model} · Higher: ${brain.higher_model}${brain.higher_configured ? " · configured" : " · higher brain disabled/unconfigured"}` : "Brain routing configuration unavailable."}
        />
      </div>

      {/* Metrics — honestly unavailable (no metrics endpoint exists) */}
      <Card className="mt-3">
        <CardHeader>
          <h2 className="text-sm font-semibold text-text">Resource metrics</h2>
        </CardHeader>
        <CardBody className="pt-3">
          <p className="text-sm text-text-secondary">Metrics unavailable</p>
          <p className="mt-1 text-xs text-text-muted">
            The backend does not expose CPU, RAM, or latency metrics.
          </p>
        </CardBody>
      </Card>

      {lastUpdated ? (
        <p className="mt-3 text-xs text-text-muted">Last updated {formatTime(lastUpdated)}</p>
      ) : null}

      {/* Sub-sections */}
      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Link href="/system/credentials">
          <Card interactive className="p-4">
            <p className="text-sm font-medium text-text">Credentials</p>
            <p className="mt-1 text-xs text-text-muted">Manage backend credentials</p>
          </Card>
        </Link>
        <Link href="/system/settings">
          <Card interactive className="p-4">
            <p className="text-sm font-medium text-text">Settings</p>
            <p className="mt-1 text-xs text-text-muted">Appearance & preferences</p>
          </Card>
        </Link>
        <Link href="/system/about">
          <Card interactive className="p-4">
            <p className="text-sm font-medium text-text">About</p>
            <p className="mt-1 text-xs text-text-muted">Version & project info</p>
          </Card>
        </Link>
      </div>
    </AppShell>
  );
}
