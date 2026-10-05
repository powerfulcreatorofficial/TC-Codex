/**
 * Engineering TC orchestrator API client (frontend).
 *
 * This is the ONLY abstraction the browser uses to talk to the orchestrator.
 * The browser NEVER executes shell commands, NEVER reaches the Rust daemon
 * directly, and NEVER stores API keys/secrets (the owner token is kept in
 * memory only — see note below).
 *
 * These types mirror the REAL backend routes defined in
 * tc-orchestrator/src/tc_orchestrator/api.py (Steps 3/4):
 *   GET  /health
 *   POST /v1/tasks                       { prompt }
 *   GET  /v1/tasks/{id}
 *   GET  /v1/tasks/{id}/events
 *   GET  /v1/tasks/{id}/pending_approval   (requires owner token header)
 *   POST /v1/tasks/{id}/approve            (requires owner token header)
 *   POST /v1/tasks/{id}/reject             (requires owner token header)
 *
 * The owner token is returned by the backend in the `x-tc-owner-token`
 * response header on task creation. The frontend keeps it in memory (React
 * state) for the session — it is NOT persisted to localStorage and NOT logged.
 */

export type TaskStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "AWAITING_APPROVAL";

export interface TaskSummary {
  task_id: string;
  status: TaskStatus;
  prompt: string;
  answer: string | null;
  steps: number;
  error: string | null;
  current_step: number;
  max_steps: number;
  created_at: string | null;
  updated_at: string | null;
  project_id: string | null;
  plan_id: string | null;
}

export interface TaskEvent {
  id: number;
  task_id: string;
  ts: string;
  event_type: string;
  tool_name: string | null;
  arguments_metadata: Record<string, unknown> | null;
  result_metadata: Record<string, unknown> | null;
  status: string | null;
}

export interface ApprovalView {
  task_id: string;
  tool_name: string;
  arguments_metadata: Record<string, unknown>;
  risk_level: string;
  created_at: string;
  expires_at: string;
  nonce: string;
}

export interface ApprovalDecision {
  approved: boolean;
  nonce: string;
  decided_by?: string;
}


export interface TaskEvaluationDimension {
  key: string;
  label: string;
  score: number;
  evidence: string;
}

export interface TaskEvaluation {
  task_id: string;
  overall_score: number;
  verdict: string;
  dimensions: TaskEvaluationDimension[];
  total_events: number;
  approvals_requested: number;
  approvals_decided: number;
  repair_signals: number;
  verification_signals: number;
}

export interface Learning {
  id: number;
  task_id: string | null;
  category: string;
  lesson: string;
  evidence: string;
  score: number;
  created_at: string | null;
}


export interface RetrievedEvidence {
  kind: string;
  record_id: string;
  score: number;
  reason: string;
  text: string;
}

export interface ProjectContextRetrieval {
  project_id: string;
  query: string;
  items: RetrievedEvidence[];
  context_text: string;
}

export interface RepositoryFile {
  path: string;
  status: string;
  size: number | null;
  sha256: string | null;
  preview: string | null;
}

export interface RepositorySnapshot {
  project_id: string;
  project_path: string;
  branch: string | null;
  clean: boolean | null;
  changed_files: RepositoryFile[];
  manifests: RepositoryFile[];
  context_text: string;
}

export interface ProjectSummary {
  id: string;
  name: string;
  description: string;
  workspace_path: string;
  task_count: number;
  created_at: string | null;
  updated_at: string | null;
}


export interface ProjectContextTask {
  task_id: string;
  status: TaskStatus;
  prompt: string;
  answer: string | null;
  error: string | null;
  steps: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProjectContextLearning {
  id: number;
  category: string;
  lesson: string;
  score: number;
  created_at: string | null;
}

export interface ProjectContext {
  project: ProjectSummary;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  active_tasks: number;
  recent_tasks: ProjectContextTask[];
  recent_learnings: ProjectContextLearning[];
  context_text: string;
}


export interface ProjectContextPacket {
  project_id: string;
  generated_at: string | null;
  health: {
    total: number;
    completed: number;
    failed: number;
    active: number;
    completion_rate: number | null;
  };
  section_names: string[];
  context_text: string;
}

export interface TaskRecovery {
  task_id: string;
  recovery_class: string;
  severity: string;
  repair_attempts: number;
  max_repair_attempts: number;
  retry_allowed: boolean;
  recommended_action: string;
  evidence: string[];
}

export interface BrainRoutingStatus {
  primary_model: string;
  higher_model: string;
  higher_enabled: boolean;
  higher_configured: boolean;
  higher_max_usd: number;
  higher_max_calls: number;
  primary_input_usd_per_mtok: number;
  primary_output_usd_per_mtok: number;
  higher_input_usd_per_mtok: number;
  higher_output_usd_per_mtok: number;
}

export interface TaskBrainUsage {
  task_id: string;
  calls: Array<{
    route: string;
    model: string;
    reason: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
    fallback: boolean;
  }>;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  higher_calls: number;
  current_route: string;
}

export interface HealthResponse {
  status: string;
  daemon: string | null;
  database: string | null;
}

/** Result of task creation: the summary plus the one-time owner token (header). */
export interface TaskCreateResult {
  summary: TaskSummary;
  ownerToken: string;
}

export class OrchestratorApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "OrchestratorApiError";
  }
}

const OWNER_HEADER = "x-tc-owner-token";

/**
 * Orchestrator API client. `baseUrl` defaults to `/api` so the browser calls
 * the orchestrator through the Next.js rewrite proxy (same-origin, no CORS, no
 * backend modification). Override via NEXT_PUBLIC_ORCH_API for direct use.
 */
export class OrchestratorClient {
  constructor(private baseUrl: string = process.env.NEXT_PUBLIC_ORCH_API ?? "/api") {}

  private url(path: string): string {
    return `${this.baseUrl}${path}`;
  }

  async listLearnings(limit = 8): Promise<Learning[]> {
    return this.get<Learning[]>(`/v1/learnings?limit=${Math.max(1, Math.min(limit, 50))}`);
  }

  async listProjects(limit = 100): Promise<ProjectSummary[]> {
    return this.get<ProjectSummary[]>(`/v1/projects?limit=${Math.max(1, Math.min(limit, 200))}`);
  }

  async createProject(input: { name: string; description?: string; workspace_path: string }): Promise<ProjectSummary> {
    return this.post<ProjectSummary>("/v1/projects", input);
  }

  async getProjectRepository(projectId: string): Promise<RepositorySnapshot> {
    return this.get<RepositorySnapshot>(`/v1/projects/${projectId}/repository`);
  }

  async getProjectContext(projectId: string): Promise<ProjectContext> {
    return this.get<ProjectContext>(`/v1/projects/${projectId}/context`);
  }

  async getProjectContextPacket(projectId: string): Promise<ProjectContextPacket> {
    return this.get<ProjectContextPacket>(`/v1/projects/${projectId}/context/packet`);
  }

  async retrieveProjectContext(projectId: string, query: string, limit = 6): Promise<ProjectContextRetrieval> {
    const qs = `?q=${encodeURIComponent(query)}&limit=${encodeURIComponent(String(limit))}`;
    return this.get<ProjectContextRetrieval>(`/v1/projects/${projectId}/context/retrieve${qs}`);
  }

  async health(): Promise<HealthResponse> {
    return this.get<HealthResponse>("/health");
  }

  async brainStatus(): Promise<BrainRoutingStatus> {
    return this.get<BrainRoutingStatus>("/v1/brain");
  }

  async taskBrainUsage(taskId: string): Promise<TaskBrainUsage> {
    return this.get<TaskBrainUsage>(`/v1/tasks/${taskId}/brain`);
  }

  async createTask(prompt: string, ownerTokenRef?: { token: string }, projectId?: string, planId?: string): Promise<TaskCreateResult> {
    const resp = await fetch(this.url("/v1/tasks"), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt, ...(projectId ? { project_id: projectId } : {}), ...(planId ? { plan_id: planId } : {}) }),
    });
    const summary = await this.parse<TaskSummary>(resp);
    // The owner token is returned in a header (once); never logged or persisted.
    const ownerToken = resp.headers.get(OWNER_HEADER) ?? "";
    if (ownerTokenRef) ownerTokenRef.token = ownerToken;
    return { summary, ownerToken };
  }

  async getTask(taskId: string): Promise<TaskSummary> {
    return this.get<TaskSummary>(`/v1/tasks/${taskId}`);
  }

  async listTasks(options?: { status?: TaskStatus; limit?: number }): Promise<TaskSummary[]> {
    const params = new URLSearchParams();
    if (options?.status) params.set("status", options.status);
    if (options?.limit) params.set("limit", String(options.limit));
    const query = params.toString();
    return this.get<TaskSummary[]>(`/v1/tasks${query ? `?${query}` : ""}`);
  }

  async listEvents(taskId: string): Promise<TaskEvent[]> {
    return this.get<TaskEvent[]>(`/v1/tasks/${taskId}/events`);
  }

  async getTaskRecovery(taskId: string): Promise<TaskRecovery> {
    return this.get<TaskRecovery>(`/v1/tasks/${taskId}/recovery`);
  }

  async getTaskEvaluation(taskId: string): Promise<TaskEvaluation> {
    return this.get<TaskEvaluation>(`/v1/tasks/${taskId}/evaluation`);
  }

  eventsStreamUrl(taskId: string): string {
    return this.url(`/v1/tasks/${taskId}/events/stream`);
  }

  streamEvents(
    taskId: string,
    onEvent: (event: TaskEvent) => void,
    onError?: () => void,
  ): () => void {
    const source = new EventSource(this.url(`/v1/tasks/${taskId}/events/stream`));
    source.onmessage = (message) => {
      try {
        onEvent(JSON.parse(message.data) as TaskEvent);
      } catch {
        onError?.();
      }
    };
    source.onerror = () => onError?.();
    return () => source.close();
  }

  async getPendingApproval(taskId: string, ownerToken: string): Promise<ApprovalView> {
    return this.get<ApprovalView>(`/v1/tasks/${taskId}/pending_approval`, {
      [OWNER_HEADER]: ownerToken,
    });
  }

  async approve(
    taskId: string,
    decision: ApprovalDecision,
    ownerToken: string,
  ): Promise<TaskSummary> {
    return this.post<TaskSummary>(`/v1/tasks/${taskId}/approve`, decision, {
      [OWNER_HEADER]: ownerToken,
    });
  }

  async reject(
    taskId: string,
    decision: ApprovalDecision,
    ownerToken: string,
  ): Promise<TaskSummary> {
    return this.post<TaskSummary>(`/v1/tasks/${taskId}/reject`, decision, {
      [OWNER_HEADER]: ownerToken,
    });
  }

  async get<T>(path: string, headers?: Record<string, string>): Promise<T> {
    const resp = await fetch(this.url(path), { headers });
    return this.parse<T>(resp);
  }

  private async post<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T> {
    const resp = await fetch(this.url(path), {
      method: "POST",
      headers: { "content-type": "application/json", ...headers },
      body: JSON.stringify(body),
    });
    return this.parse<T>(resp);
  }

  private async parse<T>(resp: Response): Promise<T> {
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const body = await resp.json();
        if (body?.detail) detail = String(body.detail);
      } catch {
        /* ignore non-json error bodies */
      }
      throw new OrchestratorApiError(detail, resp.status);
    }
    return resp.json() as Promise<T>;
  }
}

/** Default client instance. Components should import this (or inject a client). */
export const orchestrator = new OrchestratorClient();
