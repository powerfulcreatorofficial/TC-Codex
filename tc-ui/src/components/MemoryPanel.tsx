"use client";

import * as React from "react";
import { BrainCircuit, ChevronRight } from "lucide-react";
import { Card, CardBody, Badge } from "@/components/primitives";
import { useLearnings } from "@/lib/hooks/use-api";
import Link from "next/link";

function label(category: string) {
  return category.replaceAll("_", " ");
}

export function MemoryPanel() {
  const { learnings, loading, error } = useLearnings(5);
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-4 py-3.5 sm:px-5">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-soft-green">
            <BrainCircuit className="h-4 w-4 text-emerald" />
          </span>
          <div>
            <p className="text-sm font-semibold text-text">TC memory</p>
            <p className="text-[10px] text-text-muted">Verified lessons from engineering runs</p>
          </div>
        </div>
        <Badge>{learnings.length} stored</Badge>
      </div>
      <CardBody>
        {loading ? (
          <p className="text-xs text-text-muted">Loading recent lessons…</p>
        ) : error ? (
          <p className="text-xs text-text-muted">Memory is unavailable right now.</p>
        ) : learnings.length === 0 ? (
          <p className="text-xs text-text-muted">TC will record useful lessons after verified task outcomes.</p>
        ) : (
          <div className="space-y-2">
            {learnings.map((item) => (
              <div key={item.id} className="rounded-xl border border-border bg-surface-2/40 px-3.5 py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-emerald">{label(item.category)}</span>
                  <span className="font-mono text-[9px] text-text-muted">score {item.score}</span>
                </div>
                <p className="mt-1.5 text-xs leading-5 text-text-secondary">{item.lesson}</p>
              </div>
            ))}
            <Link href="/system" className="inline-flex items-center gap-1 pt-1 text-[11px] font-medium text-emerald hover:underline">
              Open system view <ChevronRight className="h-3 w-3" />
            </Link>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
