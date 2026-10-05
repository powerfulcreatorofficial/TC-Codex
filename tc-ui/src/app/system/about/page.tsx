"use client";

import Link from "next/link";
import { AppShell } from "@/components/shell/AppShell";
import { Card, CardBody, Button } from "@/components/primitives";
import { TCOrb } from "@/components/signature/TCOrb";
import packageJson from "@/../package.json";

/**
 * About. Uses the real version/description from package.json — no invented
 * version numbers.
 */
export default function AboutPage() {
  return (
    <AppShell>
      <Link href="/system">
        <Button variant="ghost" size="sm">
          ← System
        </Button>
      </Link>

      <section className="mt-3 flex flex-col items-center text-center">
        <TCOrb state="idle" size={64} className="mb-3" />
        <h1 className="text-xl font-semibold tracking-tight text-text">{packageJson.name}</h1>
        <p className="mt-1 text-sm text-text-secondary">{packageJson.description}</p>
        <p className="mt-2 font-mono text-xs text-text-muted">v{packageJson.version}</p>
      </section>

      <Card className="mt-5">
        <CardBody>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-text-muted">Product</dt>
              <dd className="text-text">Engineering TC</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-text-muted">Frontend version</dt>
              <dd className="font-mono text-text">{packageJson.version}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-text-muted">Identity</dt>
              <dd className="text-text">Green / Mint / Teal</dd>
            </div>
          </dl>
          <p className="mt-4 text-xs text-text-muted">
            Engineering TC — Personal Engineering AI / Engineering Command Center. The orchestrator
            and Rust workspace daemon remain the authoritative execution and security boundaries.
          </p>
        </CardBody>
      </Card>
    </AppShell>
  );
}
