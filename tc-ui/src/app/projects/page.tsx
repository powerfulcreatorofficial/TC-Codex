"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/shell/AppShell";
import { FolderKanban, ArrowUpRight } from "lucide-react";
import { Card, CardBody, Button, Input, Textarea } from "@/components/primitives";
import { orchestrator, type ProjectSummary } from "@/lib/api/orchestrator";

export default function ProjectsPage() {
  const [projects, setProjects] = React.useState<ProjectSummary[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [workspacePath, setWorkspacePath] = React.useState("");
  const [creating, setCreating] = React.useState(false);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try { setProjects(await orchestrator.listProjects()); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load projects"); }
    finally { setLoading(false); }
  }, []);

  React.useEffect(() => { void refresh(); }, [refresh]);

  const create = async () => {
    if (!name.trim() || !workspacePath.trim()) return;
    setCreating(true); setError(null);
    try {
      const project = await orchestrator.createProject({ name: name.trim(), description: description.trim(), workspace_path: workspacePath.trim() });
      setProjects((current) => [project, ...current.filter((p) => p.id !== project.id)]);
      setName(""); setDescription(""); setWorkspacePath("");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not create project"); }
    finally { setCreating(false); }
  };

  return <AppShell>
    <div className="flex items-end justify-between gap-4">
      <div><h1 className="text-xl font-semibold tracking-tight text-text">Projects</h1><p className="mt-1 text-xs text-text-muted">Persistent engineering workspaces for TC.</p></div>
      <Button variant="ghost" size="sm" onClick={refresh} loading={loading}>Refresh</Button>
    </div>
    {error ? <p className="mt-3 rounded-md bg-error/10 px-3 py-2 text-xs text-error" role="alert">{error}</p> : null}
    <Card className="mt-4"><CardBody className="space-y-3">
      <div className="flex items-center gap-2"><FolderKanban className="h-4 w-4 text-emerald" /><p className="text-sm font-medium text-text">Create project</p></div>
      <div className="grid gap-3 md:grid-cols-2">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Project name" aria-label="Project name" />
        <Input value={workspacePath} onChange={(e) => setWorkspacePath(e.target.value)} placeholder="Workspace path" aria-label="Workspace path" />
      </div>
      <Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What is TC building here?" aria-label="Project description" />
      <div className="flex justify-end"><Button variant="primary" size="sm" onClick={create} loading={creating} disabled={!name.trim() || !workspacePath.trim()}>Create project</Button></div>
    </CardBody></Card>
    <div className="mt-4 grid gap-3 md:grid-cols-2">
      {projects.map((project) => <Link href={`/projects/${project.id}`} key={project.id}><Card className="h-full transition hover:-translate-y-0.5 hover:shadow-elevated"><CardBody>
        <div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold text-text">{project.name}</h2><p className="mt-1 text-xs text-text-muted">{project.workspace_path}</p></div><span className="rounded-pill border border-border bg-soft-green px-2 py-1 text-[11px] font-medium text-emerald">{project.task_count} tasks</span></div>
        <p className="mt-3 text-sm text-text-secondary">{project.description || "No project description yet."}</p><div className="mt-4 flex items-center gap-1 text-xs font-medium text-emerald">Open workspace <ArrowUpRight className="h-3.5 w-3.5" /></div>
      </CardBody></Card></Link>)}
    </div>
    {!loading && projects.length === 0 ? <Card className="mt-4"><CardBody className="py-12 text-center text-sm text-text-secondary">No projects yet. Create the first workspace above.</CardBody></Card> : null}
  </AppShell>;
}
