export interface Project {
  id: number;
  name: string;
  root_path: string;
  default_branch: string;
  localforge_config_path?: string;
}

export interface Epic {
  id: number;
  project_id: number;
  title: string;
  summary: string;
  priority: number;
  status: string;
}

export interface Task {
  id: number;
  project_id: number;
  epic_id?: number;
  key: string;
  title: string;
  description: string;
  status: string;
  dependency_task_ids: number[];
  risk_level?: string;
  acceptance_criteria?: string[];
}

export interface Run {
  id: number;
  project_id: number;
  mode: string;
  initiated_by: string;
  status: string;
  started_at?: string;
  ended_at?: string;
  summary?: string;
}

export interface Agent {
  id: number;
  name: string;
  role: string;
  status: string;
  current_task_run_id?: number;
}

export interface Artifact {
  id: number;
  task_run_id: number;
  type: string;
  path: string;
  checksum: string;
  created_at: string;
}

export interface AuditEvent {
  id: number;
  project_id: number;
  run_id?: number;
  actor_type: string;
  actor_id: string;
  event_type: string;
  payload_redacted: Record<string, any>;
  created_at: string;
}

export interface Policy {
  id: number;
  project_id: number;
  name: string;
  rules: Record<string, any>;
}

export interface ActionApproval {
  id: number;
  project_id: number;
  run_id?: number;
  task_id?: number;
  kind: string;
  payload: Record<string, any>;
  status: string;
  created_at: string;
  decided_at?: string;
  decided_by?: string;
}

export interface ModelsResponse {
  provider: string;
  models: string[];
}

export interface ArtifactContent {
  id: number;
  path: string;
  content: string;
}

export interface ImportPRDResult {
  persisted: boolean;
  document_hash: string;
  changed: boolean;
  epics_created: number;
  tasks_created: number;
  epics: string[];
  tasks: string[];
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Request failed with status ${response.status}`);
  }
  return response.json();
}

export const apiClient = {
  fetchProjects(): Promise<Project[]> {
    return request<Project[]>('/api/projects');
  },

  fetchTasks(projectId: number): Promise<Task[]> {
    return request<Task[]>(`/api/projects/${projectId}/tasks`);
  },

  fetchEpics(projectId: number): Promise<Epic[]> {
    return request<Epic[]>(`/api/projects/${projectId}/epics`);
  },

  importPRD(projectId: number, path: string, dryRun: boolean): Promise<ImportPRDResult> {
    return request<ImportPRDResult>(`/api/projects/${projectId}/import-prd`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, dry_run: dryRun }),
    });
  },

  updateTask(taskId: number, payload: Partial<Task>): Promise<Task> {
    return request<Task>(`/api/tasks/${taskId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  approveTask(taskId: number): Promise<Task> {
    return request<Task>(`/api/tasks/${taskId}/approve`, {
      method: 'POST',
    });
  },

  fetchRuns(projectId: number): Promise<Run[]> {
    return request<Run[]>(`/api/projects/${projectId}/runs`);
  },

  fetchAgents(): Promise<Agent[]> {
    return request<Agent[]>('/api/agents');
  },

  fetchTaskArtifacts(task_id: number): Promise<Artifact[]> {
    return request<Artifact[]>(`/api/tasks/${task_id}/artifacts`);
  },

  fetchPolicy(projectId: number, name: string): Promise<Policy> {
    return request<Policy>(`/api/projects/${projectId}/policies/${name}`);
  },

  fetchModels(): Promise<ModelsResponse> {
    return request<ModelsResponse>('/api/models');
  },

  fetchPRs(projectId: number): Promise<Task[]> {
    return request<Task[]>(`/api/projects/${projectId}/prs`);
  },

  fetchAuditEvents(projectId: number): Promise<AuditEvent[]> {
    return request<AuditEvent[]>(`/api/projects/${projectId}/audit-events`);
  },

  commandRun(runId: number, action: 'start' | 'pause' | 'resume' | 'stop'): Promise<Run> {
    return request<Run>(`/api/runs/${runId}/${action}`, { method: 'POST' });
  },

  fetchPendingApprovals(projectId: number): Promise<ActionApproval[]> {
    return request<ActionApproval[]>(`/api/projects/${projectId}/safety/pending`);
  },

  decideApproval(
    approvalId: number,
    action: 'approve' | 'reject'
  ): Promise<ActionApproval> {
    return request<ActionApproval>(`/api/safety/approvals/${approvalId}/${action}`, {
      method: 'POST',
    });
  },

  fetchArtifactContent(artifactId: number): Promise<ArtifactContent> {
    return request<ArtifactContent>(`/api/artifacts/${artifactId}/content`);
  },
};

