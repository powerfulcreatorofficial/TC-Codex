"use client";

import Link from "next/link";
import { AppShell } from "@/components/shell/AppShell";
import { Card, CardBody, Button } from "@/components/primitives";

/**
 * Credentials screen.
 *
 * The backend exposes NO credentials endpoints (verified: no credential routes
 * in tc-orchestrator api.py). Therefore this screen shows an honest empty state
 * and does NOT fake a credential list, creation, or revocation. Credential
 * values are never stored or displayed anywhere in the browser. When the
 * backend adds credential management, this scaffold is ready to wire to it.
 */
export default function CredentialsPage() {
  return (
    <AppShell>
      <Link href="/system">
        <Button variant="ghost" size="sm">
          ← System
        </Button>
      </Link>
      <h1 className="mt-2 text-xl font-semibold tracking-tight text-text">Credentials</h1>
      <p className="mt-1 text-xs text-text-muted">
        Credential values are never stored or displayed in the browser.
      </p>

      <Card className="mt-4">
        <CardBody className="py-12 text-center">
          <p className="text-sm text-text-secondary">No credentials configured.</p>
          <p className="mt-2 text-xs text-text-muted">
            The orchestrator does not yet expose credential management. Credential storage and
            retrieval are handled securely by the backend; the browser never receives secret values.
          </p>
          <Link href="/system" className="mt-4 inline-block">
            <Button variant="secondary" size="sm">
              Back to System
            </Button>
          </Link>
        </CardBody>
      </Card>
    </AppShell>
  );
}
