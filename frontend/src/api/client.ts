export interface Project {
  id: number;
  name: string;
  root_path: string;
  default_branch: string;
  localforge_config_path?: string;
}

export interface ChatFolder {
  id: number;
  name: string;
  icon: string;
  created_at?: string;
  updated_at?: string;
}

export interface ChatSession {
  id: number;
  title: string;
  folder_id?: number | null;
  project_id?: number | null;
  message_count?: number;
  messages?: ChatMessageItem[];
  created_at?: string;
  updated_at?: string;
}

export interface ChatMessageItem {
  id: number;
  session_id: number;
  sender: 'PO' | 'Scrum Master' | 'System';
  text: string;
  attachments?: string[];
  created_at?: string;
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
  metadata?: {
    task_contract?: {
      seniority_class?: string;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
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
  model_profile_id?: string;
  active?: boolean;
  max_concurrent_tasks?: number;
  current_task_id?: number;
}

export interface TaskRun {
  id: number;
  run_id: number;
  task_id: number;
  status: string;
  worktree_path?: string;
  branch_name?: string;
  sandbox_id?: string;
  attempt_count: number;
  started_at: string;
  ended_at?: string;
  final_summary?: string;
}

export interface Handoff {
  id: number;
  task_run_id: number;
  from_role: string;
  to_role: string;
  kind: string;
  payload_json: Record<string, unknown>;
  priority: number;
  status: string;
  created_at: string;
  consumed_at?: string;
}

export interface AgentDetails {
  agent: Agent;
  current_task?: Task;
  latest_run?: TaskRun;
  handoffs: Handoff[];
  artifacts: Artifact[];
  actions: ActionApproval[];
  logs: AuditEvent[];
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
  payload_redacted: Record<string, unknown>;
  created_at: string;
}

export interface Policy {
  id: number;
  project_id: number;
  name: string;
  rules: Record<string, unknown>;
}

export interface ActionApproval {
  id: number;
  project_id: number;
  run_id?: number;
  task_id?: number;
  kind: string;
  payload: Record<string, unknown>;
  status: string;
  created_at: string;
  decided_at?: string;
  decided_by?: string;
}

export interface ModelsResponse {
  provider: string;
  models: string[];
}

export interface ModelRoute {
  id: number;
  project_id: number;
  role: string;
  provider: string;
  model_profile_id: string;
  endpoint_url?: string;
  fallback_model_profile_id?: string;
  updated_at: string;
}

export interface MemoryFact {
  id: number;
  project_id: number;
  kind: string;
  fact: string;
  source: string;
  pinned: boolean;
  status: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface SkillDefinition {
  name: string;
  purpose: string;
  system_prompt?: string;
  triggers: string[];
  allowed_actions: string[];
  expected_artifacts: string[];
  failure_modes: string[];
  examples: string[];
  strategy?: 'auto' | 'predict' | 'code_act';
  max_retries?: number;
  context_budget?: number;
  runtime?: 'instruction' | 'python';
  entrypoint?: string;
  permissions?: string[];
  dependencies?: string[];
  manifest_version?: number;
  source: string;
  enabled?: boolean;
  last_used_at?: string;
  success_rate?: number;
}

export interface EngineeringSession {
  id: string;
  project_id: number;
  title: string;
  status: string;
  current_goal_id?: string | null;
  revision: number;
}

export interface ReferenceSource {
  id: string;
  name: string;
  source_type: string;
  content_hash: string;
  injection_status: string;
  redaction_status: string;
}

export interface ReferenceHit {
  chunk_id: string;
  source_id: string;
  score: number;
  text: string;
  section?: string;
  line_start: number;
  line_end: number;
  citation: string;
}

export interface Automation {
  id: string;
  name: string;
  status: string;
  trigger_kind: string;
  next_run_at?: string | null;
}

export interface WorktreeInfo {
  task_id: number;
  task_key: string;
  task_status: string;
  branch?: string;
  path: string;
  dirty: boolean;
  last_commit?: string;
  pr_link?: string;
  cleanup_eligible: boolean;
}

export interface ModelMetric {
  role: string;
  provider: string;
  model_profile_id: string;
  success_rate: number;
  failure_rate: number;
  last_used_at?: string;
}

export interface ChiefEngineerCall {
  id: number;
  run_id?: number;
  task_id?: number;
  provider: string;
  model: string;
  reason: string;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  status: string;
  error_summary?: string;
  duration_ms: number;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ChiefEngineerUsage {
  provider: string;
  model: string;
  enabled: boolean;
  api_key_configured: boolean;
  budget: Record<string, unknown>;
  calls: ChiefEngineerCall[];
}

export interface ProjectSettings {
  project_path: string;
  default_branch: string;
  git_provider: string;
  pr_provider: string;
  remote_url?: string;
  model_endpoint: string;
  sandbox_mode: string;
  resource_limits: Record<string, unknown>;
  ui_preferences: Record<string, unknown>;
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

export interface PRDetails {
  summary: string;
  changed_files: string[];
  tests_content: string;
  risk_content: string;
  repair_content: string;
  patch_content: string;
  artifacts: Artifact[];
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const headers = {
    'Content-Type': 'application/json',
    ...(options?.headers || {}),
  };
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const detailMsg =
      typeof errorData.detail === 'string'
        ? errorData.detail
        : Array.isArray(errorData.detail)
        ? errorData.detail.map((d: unknown) => {
            if (typeof d === 'object' && d !== null && 'msg' in d) {
              return String(d.msg);
            }
            return JSON.stringify(d);
          }).join(', ')
        : `Request failed with status ${response.status}`;
    throw new Error(detailMsg);
  }
  return response.json();
}

export const apiClient = {
  fetchProjects(): Promise<Project[]> {
    return request<Project[]>('/api/projects');
  },

  createProject(payload: { name: string; root_path?: string }): Promise<Project> {
    return request<Project>('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  poChat(
    message: string,
    attachments?: string[],
    projectId?: number
  ): Promise<{ project: Project; reply: string; status: string }> {
    return request<{ project: Project; reply: string; status: string }>('/api/projects/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, attachments, project_id: projectId }),
    });
  },

  intakeProjectInputs(payload: {
    name: string;
    root_path: string;
    project_id?: number;
    prd_content: string;
    design_image_name?: string;
    design_image_base64?: string;
  }): Promise<{
    project: Project;
    prd_path: string;
    design_image_path: string | null;
    prd_import: ImportPRDResult;
  }> {
    return request('/api/projects/intake', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  startSquad(projectId: number): Promise<{ status: string; run_id: number; message: string }> {
    return request<{ status: string; run_id: number; message: string }>(`/api/projects/${projectId}/start-squad`, {
      method: 'POST',
    });
  },

  resetAll(): Promise<{ status: string; message: string }> {
    return request<{ status: string; message: string }>('/api/projects/reset-all', {
      method: 'POST',
    });
  },

  fetchTelemetrySpans(projectId: number): Promise<unknown[]> {
    return request<unknown[]>(`/api/projects/${projectId}/telemetry-spans`);
  },

  fetchTelemetryEvents(projectId: number): Promise<unknown[]> {
    return request<unknown[]>(`/api/projects/${projectId}/telemetry-events`);
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

  fetchPolicy(projectId: number, name: string): Promise<Policy | null> {
    return request<Policy>(`/api/projects/${projectId}/policies/${name}`).catch(() => null);
  },

  updatePolicy(
    projectId: number,
    name: string,
    rules: Record<string, unknown>
  ): Promise<Policy> {
    return request<Policy>(`/api/projects/${projectId}/policies/${name}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(rules),
    });
  },

  fetchModels(): Promise<ModelsResponse> {
    return request<ModelsResponse>('/api/models');
  },

  fetchSkills(projectId: number): Promise<SkillDefinition[]> {
    return request<SkillDefinition[]>(`/api/projects/${projectId}/skills`);
  },

  createSkill(projectId: number, payload: Partial<SkillDefinition>): Promise<SkillDefinition> {
    return request<SkillDefinition>(`/api/projects/${projectId}/skills`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  updateSkill(
    projectId: number,
    name: string,
    payload: Partial<SkillDefinition>
  ): Promise<SkillDefinition> {
    return request<SkillDefinition>(`/api/projects/${projectId}/skills/${name}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  fetchEngineeringSessions(projectId: number): Promise<EngineeringSession[]> {
    return request<EngineeringSession[]>(`/api/projects/${projectId}/engineering/sessions`);
  },

  fetchReferences(projectId: number): Promise<ReferenceSource[]> {
    return request<ReferenceSource[]>(`/api/projects/${projectId}/references`);
  },

  searchReferences(projectId: number, query: string): Promise<ReferenceHit[]> {
    return request<ReferenceHit[]>(`/api/projects/${projectId}/references/search`, {
      method: 'POST',
      body: JSON.stringify({ query, limit: 8 }),
    });
  },

  fetchAutomations(projectId: number): Promise<Automation[]> {
    return request<Automation[]>(`/api/projects/${projectId}/automations`);
  },

  discoverModelCatalog(projectId: number): Promise<Record<string, unknown>[]> {
    return request<Record<string, unknown>[]>(`/api/projects/${projectId}/models/catalog/discover`, { method: 'POST' });
  },

  fetchSkillManifest(projectId: number, name: string): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>(`/api/projects/${projectId}/skills/${name}/manifest`);
  },

  deleteSkill(projectId: number, name: string): Promise<{ status: string; name: string }> {
    return request<{ status: string; name: string }>(`/api/projects/${projectId}/skills/${name}`, {
      method: 'DELETE',
    });
  },

  fetchWorktrees(projectId: number): Promise<WorktreeInfo[]> {
    return request<WorktreeInfo[]>(`/api/projects/${projectId}/worktrees`);
  },

  cleanupWorktree(taskId: number): Promise<{ status: string }> {
    return request<{ status: string }>(`/api/tasks/${taskId}/worktree/cleanup`, {
      method: 'POST',
    });
  },

  revertWorktree(taskId: number, checkpointHash: string): Promise<{ status: string }> {
    return request<{ status: string }>(`/api/tasks/${taskId}/worktree/revert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ checkpoint_hash: checkpointHash }),
    });
  },

  fetchModelMetrics(projectId: number): Promise<ModelMetric[]> {
    return request<ModelMetric[]>(`/api/projects/${projectId}/models/metrics`);
  },

  fetchChiefEngineerUsage(projectId: number): Promise<ChiefEngineerUsage> {
    return request<ChiefEngineerUsage>(`/api/projects/${projectId}/chief-engineer/calls`);
  },

  fetchProjectSettings(projectId: number): Promise<ProjectSettings> {
    return request<ProjectSettings>(`/api/projects/${projectId}/settings`);
  },

  exportAuditEvents(projectId: number): Promise<string> {
    return fetch(`/api/projects/${projectId}/audit-events/export`).then((res) => {
      if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
      return res.text();
    });
  },

  lockProject(projectId: number): Promise<Policy> {
    return request<Policy>(`/api/projects/${projectId}/lock`, { method: 'POST' });
  },

  fetchModelRoutes(projectId: number): Promise<ModelRoute[]> {
    return request<ModelRoute[]>(`/api/projects/${projectId}/model-routes`);
  },

  saveModelRoute(projectId: number, payload: Partial<ModelRoute>): Promise<ModelRoute> {
    return request<ModelRoute>(`/api/projects/${projectId}/model-routes`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  fetchMemoryFacts(projectId: number): Promise<MemoryFact[]> {
    return request<MemoryFact[]>(`/api/projects/${projectId}/memory`);
  },

  createMemoryFact(projectId: number, payload: Partial<MemoryFact>): Promise<MemoryFact> {
    return request<MemoryFact>(`/api/projects/${projectId}/memory`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  updateMemoryFact(factId: number, payload: Partial<MemoryFact>): Promise<MemoryFact> {
    return request<MemoryFact>(`/api/memory/${factId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  deleteMemoryFact(factId: number): Promise<{ status: string }> {
    return request<{ status: string }>(`/api/memory/${factId}`, { method: 'DELETE' });
  },

  exportMemory(projectId: number, format: 'json' | 'yaml'): Promise<string> {
    return fetch(`/api/projects/${projectId}/memory/export?format=${format}`).then((res) => {
      if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
      return res.text();
    });
  },

  importMemory(projectId: number, format: 'json' | 'yaml', payload: string): Promise<MemoryFact[]> {
    return request<MemoryFact[]>(`/api/projects/${projectId}/memory/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format, payload }),
    });
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

  fetchPRDetails(taskId: number): Promise<PRDetails> {
    return request<PRDetails>(`/api/tasks/${taskId}/pr-details`);
  },

  openLocalPath(taskId: number): Promise<{ status: string; path: string }> {
    return request<{ status: string; path: string }>(`/api/tasks/${taskId}/open-path`, {
      method: 'POST',
    });
  },

  rerunTests(taskId: number): Promise<{ exit_code: number; stdout: string; stderr: string }> {
    return request<{ exit_code: number; stdout: string; stderr: string }>(
      `/api/tasks/${taskId}/rerun-tests`,
      { method: 'POST' }
    );
  },

  decidePRReview(
    taskId: number,
    action: 'accept' | 'reject' | 'request_adjustment'
  ): Promise<Task> {
    return request<Task>(`/api/tasks/${taskId}/pr-review/${action}`, {
      method: 'POST',
    });
  },

  fetchAgentDetails(agentId: number): Promise<AgentDetails> {
    return request<AgentDetails>(`/api/agents/${agentId}/details`);
  },

  controlTaskExecution(
    taskId: number,
    action: 'pause' | 'resume' | 'terminate' | 'block'
  ): Promise<Task> {
    return request<Task>(`/api/tasks/${taskId}/control/${action}`, {
      method: 'POST',
    });
  },

  restorePolicyVersion(
    projectId: number,
    name: string,
    version: number
  ): Promise<Policy> {
    return request<Policy>(
      `/api/projects/${projectId}/policies/${name}/restore/${version}`,
      { method: 'POST' }
    );
  },

  approvePR(taskId: number): Promise<Task> {
    return request<Task>(`/api/tasks/${taskId}/prs/approve`, {
      method: 'POST',
    });
  },

  rejectPR(taskId: number, comment: string): Promise<Task> {
    return request<Task>(`/api/tasks/${taskId}/prs/reject`, {
      method: 'POST',
      body: JSON.stringify({ comment }),
    });
  },

  getEnvSettings(): Promise<Record<string, string>> {
    return request<Record<string, string>>('/api/settings/env');
  },

  updateEnvSettings(envVars: Record<string, string>): Promise<Record<string, string>> {
    return request<Record<string, string>>('/api/settings/env', {
      method: 'POST',
      body: JSON.stringify(envVars),
    });
  },

  // Chat Folders CRUD
  fetchChatFolders(): Promise<ChatFolder[]> {
    return request<ChatFolder[]>('/api/chat/folders');
  },

  createChatFolder(name: string, icon = 'folder'): Promise<ChatFolder> {
    return request<ChatFolder>('/api/chat/folders', {
      method: 'POST',
      body: JSON.stringify({ name, icon }),
    });
  },

  updateChatFolder(folderId: number, data: { name?: string; icon?: string }): Promise<ChatFolder> {
    return request<ChatFolder>(`/api/chat/folders/${folderId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  deleteChatFolder(folderId: number): Promise<{ status: string; folder_id: number }> {
    return request<{ status: string; folder_id: number }>(`/api/chat/folders/${folderId}`, {
      method: 'DELETE',
    });
  },

  // Chat Sessions CRUD
  fetchChatSessions(): Promise<ChatSession[]> {
    return request<ChatSession[]>('/api/chat/sessions');
  },

  createChatSession(title = 'Nova Conversa', folderId?: number | null): Promise<ChatSession> {
    return request<ChatSession>('/api/chat/sessions', {
      method: 'POST',
      body: JSON.stringify({ title, folder_id: folderId }),
    });
  },

  fetchChatSessionDetails(sessionId: number): Promise<ChatSession> {
    return request<ChatSession>(`/api/chat/sessions/${sessionId}`);
  },

  updateChatSession(
    sessionId: number,
    data: { title?: string; folder_id?: number | null; project_id?: number | null }
  ): Promise<ChatSession> {
    return request<ChatSession>(`/api/chat/sessions/${sessionId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  deleteChatSession(sessionId: number): Promise<{ status: string; session_id: number }> {
    return request<{ status: string; session_id: number }>(`/api/chat/sessions/${sessionId}`, {
      method: 'DELETE',
    });
  },

  poScrumMasterChat(
    message: string,
    attachments: string[],
    projectId?: number,
    sessionId?: number,
    prdPath?: string
  ): Promise<{ project: Project; reply: string; session_id: number; status: string }> {
    return request<{ project: Project; reply: string; session_id: number; status: string }>(
      '/api/projects/chat',
      {
        method: 'POST',
        body: JSON.stringify({
          message,
          attachments,
          project_id: projectId,
          session_id: sessionId,
          prd_path: prdPath,
        }),
      }
    );
  },
};
