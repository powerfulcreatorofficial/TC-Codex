/**
 * DEMO DATA — for isolated component previews only.
 *
 * This file is NOT production API state. It exists so the design-system
 * showcase page can render signature components without faking backend
 * responses. Real task data comes only from `OrchestratorClient`.
 *
 * Nothing here pretends to be a real task; it is clearly synthetic fixture data
 * used purely to demonstrate visual states.
 */

import type { ActivityItem } from "@/components/signature/ActivityTimeline";
import type { TaskStatus } from "./orchestrator";

export interface DemoTask {
  task_id: string;
  status: TaskStatus;
  prompt: string;
  current_step: number;
  max_steps: number;
  created_at: string | null;
}

export const demoTasks: DemoTask[] = [
  {
    task_id: "demo-0001",
    status: "COMPLETED",
    prompt: "Read README.md and summarize the repository purpose",
    current_step: 2,
    max_steps: 20,
    created_at: "2026-08-27T12:00:00Z",
  },
  {
    task_id: "demo-0002",
    status: "AWAITING_APPROVAL",
    prompt: "Refactor the auth module and run tests",
    current_step: 4,
    max_steps: 20,
    created_at: "2026-08-27T12:10:00Z",
  },
];

export const demoActivity: ActivityItem[] = [
  { id: 1, title: "read_file · README.md", meta: "completed · 12ms", tone: "success" },
  { id: 2, title: "exec_command · cargo test", meta: "approved · 1.2s", tone: "teal" },
  { id: 3, title: "write_file · src/auth.rs", meta: "awaiting approval", tone: "warning" },
];

export const demoApproval = {
  toolName: "write_file",
  riskLevel: "L1",
  argumentsSummary: {
    path: "src/auth.rs",
    content_length: 1284,
    content_preview: "pub fn authorize(...) -> bool {",
  },
  expiresAt: "in 4m 59s",
  nonce: "demo-nonce-not-real",
};
