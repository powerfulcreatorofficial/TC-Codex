"use client";
import * as React from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/shell/AppShell";
import { Card, CardBody, Button, Skeleton, Badge } from "@/components/primitives";
import { orchestrator, type ProjectContext, type ProjectSummary, type ProjectContextRetrieval, type ProjectContextPacket, type RepositorySnapshot } from "@/lib/api/orchestrator";

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const [project, setProject] = React.useState<ProjectSummary | null>(null);
  const [context, setContext] = React.useState<ProjectContext | null>(null);
  const [packet, setPacket] = React.useState<ProjectContextPacket | null>(null);
  const [retrieval, setRetrieval] = React.useState<ProjectContextRetrieval | null>(null);
  const [repository, setRepository] = React.useState<RepositorySnapshot | null>(null);
  const [query, setQuery] = React.useState("");
  const [retrieving, setRetrieving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    Promise.all([
      orchestrator.get<ProjectSummary>(`/v1/projects/${params.id}`),
      orchestrator.getProjectContext(params.id),
      orchestrator.getProjectContextPacket(params.id),
      orchestrator.getProjectRepository(params.id),
    ])
      .then(([nextProject, nextContext, nextPacket, nextRepository]) => {
        if (!cancelled) {
          setProject(nextProject);
          setContext(nextContext);
          setPacket(nextPacket);
          setRepository(nextRepository);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load project");
      });
    return () => { cancelled = true; };
  }, [params.id]);


  const runRetrieval = async () => {
    if (!query.trim()) return;
    setRetrieving(true);
    try { setRetrieval(await orchestrator.retrieveProjectContext(params.id, query.trim(), 6)); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not retrieve project context"); }
    finally { setRetrieving(false); }
  };

  return <AppShell>
    <Link href="/projects" className="text-xs text-emerald">← Projects</Link>
    {error ? <p className="mt-4 rounded-md bg-error/10 px-3 py-2 text-xs text-error">{error}</p> : null}
    {!project && !error ? <Skeleton className="mt-4 h-32 w-full rounded-xl" /> : null}
    {project ? <section className="mt-4 space-y-4">
      <div>
        <p className="text-[11px] uppercase tracking-[0.2em] text-text-muted">Engineering project</p>
        <h1 className="mt-1 text-2xl font-semibold text-text">{project.name}</h1>
        <p className="mt-1 text-sm text-text-secondary">{project.description || "No description"}</p>
      </div>

      <Card><CardBody className="grid gap-4 sm:grid-cols-4">
        <div><p className="text-xs text-text-muted">Workspace</p><p className="mt-1 text-sm font-medium text-text break-all">{project.workspace_path}</p></div>
        <div><p className="text-xs text-text-muted">Total tasks</p><p className="mt-1 text-2xl font-semibold text-text">{context?.total_tasks ?? project.task_count}</p></div>
        <div><p className="text-xs text-text-muted">Completed</p><p className="mt-1 text-2xl font-semibold text-emerald">{context?.completed_tasks ?? 0}</p></div>
        <div className="sm:text-right"><Link href="/"><Button size="sm" variant="primary">Start task</Button></Link></div>
      </CardBody></Card>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Card><CardBody>
          <div className="flex items-center justify-between"><div><h2 className="text-sm font-semibold text-text">Recent engineering runs</h2><p className="mt-1 text-xs text-text-muted">Actual persisted task history for this project.</p></div><Badge variant="outline">{context?.active_tasks ?? 0} active</Badge></div>
          <div className="mt-4 space-y-2">
            {context?.recent_tasks.length ? context.recent_tasks.map((task) => <Link key={task.task_id} href={`/tasks/${task.task_id}`} className="block rounded-lg border border-border p-3 transition-colors hover:bg-surface-muted">
              <div className="flex items-center justify-between gap-3"><p className="truncate text-sm font-medium text-text">{task.prompt}</p><Badge variant={task.status === "COMPLETED" ? "success" : task.status === "FAILED" ? "error" : "outline"}>{task.status}</Badge></div>
              <p className="mt-1 text-[11px] text-text-muted">{task.steps} steps · {task.updated_at ? new Date(task.updated_at).toLocaleString() : "recent"}</p>
            </Link>) : <p className="py-8 text-center text-xs text-text-muted">No project tasks yet.</p>}
          </div>
        </CardBody></Card>

        <Card><CardBody>
          <h2 className="text-sm font-semibold text-text">Project memory</h2>
          <p className="mt-1 text-xs text-text-muted">Verified lessons associated with this project.</p>
          <div className="mt-4 space-y-3">
            {context?.recent_learnings.length ? context.recent_learnings.map((item) => <div key={item.id} className="rounded-lg bg-surface-muted p-3"><div className="flex items-center justify-between"><Badge variant="outline">{item.category}</Badge><span className="text-[11px] text-text-muted">score {item.score}</span></div><p className="mt-2 text-xs leading-5 text-text-secondary">{item.lesson}</p></div>) : <p className="py-8 text-center text-xs text-text-muted">No verified project lessons yet.</p>}
          </div>
        </CardBody></Card>
      </div>

      <Card><CardBody>
        <div className="flex items-center justify-between gap-3"><div><h2 className="text-sm font-semibold text-text">Relevant memory retrieval</h2><p className="mt-1 text-xs text-text-muted">Preview which persisted project evidence TC would retrieve for a task.</p></div><Badge variant="outline">deterministic</Badge></div>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row"><input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void runRetrieval(); }} placeholder="e.g. fix authentication tests" className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:ring-2 focus:ring-emerald/30" /><Button size="sm" variant="primary" onClick={runRetrieval} loading={retrieving} disabled={!query.trim()}>Retrieve</Button></div>
        <div className="mt-4 space-y-2">{retrieval?.items.length ? retrieval.items.map((item) => <div key={`${item.kind}:${item.record_id}`} className="rounded-lg bg-surface-muted p-3"><div className="flex items-center justify-between gap-3"><Badge variant="outline">{item.kind}</Badge><span className="text-[11px] text-text-muted">score {item.score}</span></div><p className="mt-2 text-xs leading-5 text-text-secondary">{item.text}</p><p className="mt-1 text-[11px] text-text-muted">{item.reason}</p></div>) : retrieval ? <p className="py-6 text-center text-xs text-text-muted">No relevant evidence met the retrieval threshold.</p> : <p className="py-6 text-center text-xs text-text-muted">Enter a task topic to preview retrieved evidence.</p>}</div>
      </CardBody></Card>


      <Card><CardBody>
        <div className="flex items-center justify-between gap-3"><div><h2 className="text-sm font-semibold text-text">Current repository state</h2><p className="mt-1 text-xs text-text-muted">Read-only evidence captured through the workspace daemon.</p></div><Badge variant={repository?.clean ? "success" : "outline"}>{repository?.clean ? "clean" : repository ? "changes detected" : "loading"}</Badge></div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg bg-surface-muted p-3"><p className="text-[11px] text-text-muted">Branch</p><p className="mt-1 truncate text-sm font-semibold text-text">{repository?.branch ?? "—"}</p></div>
          <div className="rounded-lg bg-surface-muted p-3"><p className="text-[11px] text-text-muted">Changed files</p><p className="mt-1 text-lg font-semibold text-text">{repository?.changed_files.length ?? 0}</p></div>
          <div className="rounded-lg bg-surface-muted p-3"><p className="text-[11px] text-text-muted">Detected manifests</p><p className="mt-1 text-lg font-semibold text-text">{repository?.manifests.length ?? 0}</p></div>
        </div>
        {repository?.changed_files.length ? <div className="mt-4 space-y-2">{repository.changed_files.map((file) => <div key={`${file.status}:${file.path}`} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2"><span className="truncate font-mono text-xs text-text">{file.path}</span><Badge variant="outline">{file.status}</Badge></div>)}</div> : <p className="mt-4 py-4 text-center text-xs text-text-muted">No project-scoped changes observed.</p>}
      </CardBody></Card>

      <Card><CardBody>
        <div className="flex items-center justify-between gap-3"><div><h2 className="text-sm font-semibold text-text">Context engine</h2><p className="mt-1 text-xs text-text-muted">Bounded evidence packet supplied to TC while working on this project.</p></div><Badge variant="outline">{packet?.section_names.length ?? 0} sections</Badge></div>
        <div className="mt-4 grid gap-3 sm:grid-cols-4">
          <div className="rounded-lg bg-surface-muted p-3"><p className="text-[11px] text-text-muted">Completion rate</p><p className="mt-1 text-lg font-semibold text-text">{packet?.health.completion_rate == null ? "—" : `${packet.health.completion_rate}%`}</p></div>
          <div className="rounded-lg bg-surface-muted p-3"><p className="text-[11px] text-text-muted">Completed</p><p className="mt-1 text-lg font-semibold text-emerald">{packet?.health.completed ?? 0}</p></div>
          <div className="rounded-lg bg-surface-muted p-3"><p className="text-[11px] text-text-muted">Failed</p><p className="mt-1 text-lg font-semibold text-error">{packet?.health.failed ?? 0}</p></div>
          <div className="rounded-lg bg-surface-muted p-3"><p className="text-[11px] text-text-muted">Active</p><p className="mt-1 text-lg font-semibold text-text">{packet?.health.active ?? 0}</p></div>
        </div>
        <pre className="mt-4 max-h-96 overflow-auto rounded-lg bg-surface-muted p-4 font-mono text-[11px] leading-5 text-text-secondary">{packet?.context_text ?? context?.context_text ?? "Loading project context…"}</pre>
      </CardBody></Card>
    </section> : null}
  </AppShell>;
}
