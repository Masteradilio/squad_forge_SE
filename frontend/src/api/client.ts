export interface Project {
  id: number;
  name: string;
  root_path: string;
  default_branch: string;
}

export interface Task {
  id: number;
  project_id: number;
  key: string;
  title: string;
  description: string;
  status: string;
  dependency_task_ids: number[];
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

export interface ModelsResponse {
  provider: string;
  models: string[];
}

export interface ArtifactContent {
  id: number;
  path: string;
  content: string;
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

  fetchArtifactContent(artifactId: number): Promise<ArtifactContent> {
    return request<ArtifactContent>(`/api/artifacts/${artifactId}/content`);
  },
};
