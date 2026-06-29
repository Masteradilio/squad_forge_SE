import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  apiClient,
  type Project,
  type Task,
  type Run,
  type Agent,
  type Artifact,
  type Policy,
  type ActionApproval,
  type Epic,
  type ImportPRDResult,
  type PRDetails,
  type AgentDetails,
  type MemoryFact,
  type ModelRoute,
  type ModelMetric,
  type ChiefEngineerUsage,
  type ProjectSettings,
  type SkillDefinition,
  type WorktreeInfo,
} from './api/client';
import { useProjectEvents, type LifecycleEventPayload } from './api/events';
import { Card } from './components/Card';
import { Table, type Column } from './components/Table';
import { StatusBadge } from './components/Badge';
import { Button } from './components/Button';
import { Alert } from './components/Alert';
import { Timeline, type TimelineItem } from './components/Timeline';
import { EmptyState } from './components/EmptyState';
import { CodeBlock } from './components/CodeBlock';
import { V3Dashboard } from './components/V3Dashboard';
import { KanbanBoard } from './components/KanbanBoard';


const wouldCreateCycle = (
  taskId: number,
  newDeps: number[],
  allTasks: Task[]
): boolean => {
  const tasksById = new Map(allTasks.map((task) => [task.id, task]));
  const visited = new Set<number>();
  const queue = [...newDeps];
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (current === taskId) return true;
    if (!visited.has(current)) {
      visited.add(current);
      const task = tasksById.get(current);
      if (task && task.dependency_task_ids) {
        queue.push(...task.dependency_task_ids);
      }
    }
  }
  return false;
};

const PIPELINE_ROLES = [
  'Planner',
  'Specifier',
  'Coder',
  'Cleaner',
  'Tester',
  'Fixer',
  'Reviewer',
  'Architect',
  'Hardener',
  'QA',
  'PRWriter',
];


type Tab =
  | 'mission-control'
  | 'prd-backlog'
  | 'agents'
  | 'runs'
  | 'prs'
  | 'worktrees'
  | 'models'
  | 'skills'
  | 'memory'
  | 'safety'
  | 'v3-dashboard'
  | 'kanban'
  | 'settings';

export default function App() {
  // Navigation & Project selection
  const [currentTab, setCurrentTab] = useState<Tab>('mission-control');
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);

  // Data states
  const [tasks, setTasks] = useState<Task[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [worktrees, setWorktrees] = useState<WorktreeInfo[]>([]);
  const [modelMetrics, setModelMetrics] = useState<ModelMetric[]>([]);
  const [chiefEngineerUsage, setChiefEngineerUsage] = useState<ChiefEngineerUsage | null>(null);
  const [projectSettings, setProjectSettings] = useState<ProjectSettings | null>(null);
  const [auditExport, setAuditExport] = useState('');
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [taskArtifacts, setTaskArtifacts] = useState<Artifact[]>([]);
  const [selectedArtifactContent, setSelectedArtifactContent] = useState<{
    path: string;
    content: string;
  } | null>(null);

  const [epics, setEpics] = useState<Epic[]>([]);
  const [prdPath, setPrdPath] = useState<string>('');
  const [dryRun, setDryRun] = useState<boolean>(false);
  const [importResult, setImportResult] = useState<ImportPRDResult | null>(null);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [activeEpic, setActiveEpic] = useState<Epic | null>(null);

  const [editTitle, setEditTitle] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editRisk, setEditRisk] = useState('low');
  const [editCriteria, setEditCriteria] = useState('');
  const [editDeps, setEditDeps] = useState('');

  const [backlogPage, setBacklogPage] = useState(1);
  const [missionControlPage, setMissionControlPage] = useState(1);

  // Safety Policy Editing State
  const [isEditingPolicy, setIsEditingPolicy] = useState(false);
  const [policyAllowedCmds, setPolicyAllowedCmds] = useState('');
  const [policyBlockedCmds, setPolicyBlockedCmds] = useState('');
  const [policyProtectedPaths, setPolicyProtectedPaths] = useState('');
  const [policyMaxRepair, setPolicyMaxRepair] = useState(3);
  const [policyMaxFiles, setPolicyMaxFiles] = useState(10);

  // PR Review State
  const [selectedPRTask, setSelectedPRTask] = useState<Task | null>(null);
  const [prDetails, setPrDetails] = useState<PRDetails | null>(null);
  const [isLoadingPRDetails, setIsLoadingPRDetails] = useState(false);
  const [isRerunningTests, setIsRerunningTests] = useState(false);
  const [testConsoleOutput, setTestConsoleOutput] = useState('');

  // Agent Manager State
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [agentDetails, setAgentDetails] = useState<AgentDetails | null>(null);
  const [isLoadingAgentDetails, setIsLoadingAgentDetails] = useState(false);
  const [agentDetailTab, setAgentDetailTab] = useState<'context' | 'logs' | 'handoffs'>('context');

  // Skills and Memory states
  const [projectMemory, setProjectMemory] = useState<MemoryFact[]>([]);
  const [modelRoutes, setModelRoutes] = useState<ModelRoute[]>([]);
  const [routeDrafts, setRouteDrafts] = useState<Record<string, Partial<ModelRoute>>>({});
  const [memoryExport, setMemoryExport] = useState('');
  const [memoryImport, setMemoryImport] = useState('');
  const [memoryFormat, setMemoryFormat] = useState<'json' | 'yaml'>('json');

  const [skills, setSkills] = useState<SkillDefinition[]>([]);

  const [newMemoryFact, setNewMemoryFact] = useState('');
  const [newMemoryKind, setNewMemoryKind] = useState('stack_fact');
  const [newSkillName, setNewSkillName] = useState('');
  const [newSkillTrigger, setNewSkillTrigger] = useState('');

  const handleToggleSkill = async (skill: SkillDefinition) => {
    if (!activeProject) return;
    const updated = await apiClient.updateSkill(activeProject.id, skill.name, {
      ...skill,
      enabled: !(skill.enabled ?? true),
    });
    setSkills((prev) => prev.map((item) => (item.name === skill.name ? updated : item)));
  };

  const handleAddMemoryFact = async () => {
    if (!activeProject || !newMemoryFact.trim()) return;
    const newFact = await apiClient.createMemoryFact(activeProject.id, {
      fact: newMemoryFact.trim(),
      kind: newMemoryKind,
      pinned: false,
      status: 'active',
      source: 'manual',
      tags: [],
    });
    setProjectMemory((prev) => [newFact, ...prev]);
    setNewMemoryFact('');
  };

  const handlePinMemory = async (item: MemoryFact) => {
    const updated = await apiClient.updateMemoryFact(item.id, { pinned: !item.pinned });
    setProjectMemory((prev) => prev.map((m) => (m.id === item.id ? updated : m)));
  };

  const handleStaleMemory = async (item: MemoryFact) => {
    const status = item.status === 'stale' ? 'active' : 'stale';
    const updated = await apiClient.updateMemoryFact(item.id, { status });
    setProjectMemory((prev) => prev.map((m) => (m.id === item.id ? updated : m)));
  };

  const handleDeleteMemory = async (id: number) => {
    await apiClient.deleteMemoryFact(id);
    setProjectMemory((prev) => prev.filter((m) => m.id !== id));
  };

  const handleRouteDraftChange = (
    role: string,
    field: 'provider' | 'model_profile_id' | 'endpoint_url' | 'fallback_model_profile_id',
    value: string
  ) => {
    setRouteDrafts((prev) => ({
      ...prev,
      [role]: {
        ...prev[role],
        role,
        [field]: value,
      },
    }));
  };

  const handleSaveRoute = async (role: string) => {
    if (!activeProject) return;
    const draft = routeDrafts[role];
    const model = draft?.model_profile_id || `${role.toLowerCase()}-local`;
    const saved = await apiClient.saveModelRoute(activeProject.id, {
      role,
      provider: draft?.provider || 'localforge',
      model_profile_id: model,
      endpoint_url: draft?.endpoint_url || undefined,
      fallback_model_profile_id: draft?.fallback_model_profile_id || undefined,
    });
    setModelRoutes((prev) => {
      const rest = prev.filter((route) => route.role !== role);
      return [...rest, saved].sort((a, b) => a.role.localeCompare(b.role));
    });
    setRouteDrafts((prev) => ({ ...prev, [role]: saved }));
  };

  const handleExportMemory = async () => {
    if (!activeProject) return;
    setMemoryExport(await apiClient.exportMemory(activeProject.id, memoryFormat));
  };

  const handleImportMemory = async () => {
    if (!activeProject || !memoryImport.trim()) return;
    const imported = await apiClient.importMemory(activeProject.id, memoryFormat, memoryImport);
    setProjectMemory((prev) => [...imported, ...prev]);
    setMemoryImport('');
  };

  const handleAddSkill = async () => {
    if (!activeProject || !newSkillName.trim() || !newSkillTrigger.trim()) return;
    const newSkill = await apiClient.createSkill(activeProject.id, {
      name: newSkillName.trim(),
      purpose: newSkillTrigger.trim(),
      triggers: newSkillTrigger
        .split(',')
        .map((part) => part.trim())
        .filter(Boolean),
      allowed_actions: ['read project context'],
      expected_artifacts: ['review.md'],
      failure_modes: ['trigger mismatch'],
      examples: [newSkillTrigger.trim()],
    });
    setSkills((prev) => [newSkill, ...prev.filter((skill) => skill.name !== newSkill.name)]);
    setNewSkillName('');
    setNewSkillTrigger('');
  };

  useEffect(() => {
    if (selectedAgent) {
      setIsLoadingAgentDetails(true);
      apiClient
        .fetchAgentDetails(selectedAgent.id)
        .then((details) => {
          setAgentDetails(details);
        })
        .catch((err) => {
          console.error('Error fetching agent details:', err);
          alert('Failed to load agent details.');
        })
        .finally(() => {
          setIsLoadingAgentDetails(false);
        });
    } else {
      setAgentDetails(null);
    }
  }, [selectedAgent]);

  const handleControlTask = async (
    taskId: number,
    action: 'pause' | 'resume' | 'terminate' | 'block'
  ) => {
    try {
      await apiClient.controlTaskExecution(taskId, action);
      alert(`Task execution ${action}ed successfully!`);
      if (selectedAgent) {
        const details = await apiClient.fetchAgentDetails(selectedAgent.id);
        setAgentDetails(details);
      }
      if (activeProject) {
        const tData = await apiClient.fetchTasks(activeProject.id);
        setTasks(tData);
      }
    } catch (err: any) {
      console.error('Error controlling task:', err);
      alert(`Failed to ${action} task: ${err.message}`);
    }
  };

  const handleRestorePolicyVersion = async (version: number) => {
    if (!activeProject || !policy) return;
    try {
      const updatedPolicy = await apiClient.restorePolicyVersion(
        activeProject.id,
        policy.name,
        version
      );
      setPolicy(updatedPolicy);
      alert(`Policy reverted to version ${version} successfully!`);
    } catch (err: any) {
      console.error('Error restoring policy:', err);
      alert(`Failed to restore policy version: ${err.message}`);
    }
  };

  const startEditingPolicy = () => {
    const rules = policy?.rules || {};
    setPolicyAllowedCmds((rules.allowed_commands || []).join('\n'));
    setPolicyBlockedCmds((rules.blocked_commands || []).join('\n'));
    setPolicyProtectedPaths((rules.protected_paths || []).join('\n'));
    setPolicyMaxRepair(rules.max_repair_attempts ?? 3);
    setPolicyMaxFiles(rules.max_files_touched ?? 10);
    setIsEditingPolicy(true);
  };

  const handleSavePolicy = async () => {
    if (!activeProject || !policy) return;
    try {
      const allowed = policyAllowedCmds.split('\n').map(s => s.trim()).filter(Boolean);
      const blocked = policyBlockedCmds.split('\n').map(s => s.trim()).filter(Boolean);
      const protectedP = policyProtectedPaths.split('\n').map(s => s.trim()).filter(Boolean);

      const payload = {
        name: policy.rules?.name || 'default',
        allowed_commands: allowed,
        blocked_commands: blocked,
        protected_paths: protectedP,
        max_repair_attempts: Number(policyMaxRepair),
        max_files_touched: Number(policyMaxFiles),
        approval_required_patterns: policy.rules?.approval_required_patterns || [],
        max_run_duration: policy.rules?.max_run_duration ?? null,
        allowed_directories: policy.rules?.allowed_directories || [],
      };

      await apiClient.updatePolicy(activeProject.id, 'default', payload);
      setIsEditingPolicy(false);
      loadProjectData();
      alert('Policy updated successfully!');
    } catch (err: any) {
      alert(err.message || 'Failed to update policy rules.');
    }
  };

  const loadPRDetails = useCallback((taskId: number) => {
    setIsLoadingPRDetails(true);
    setPrDetails(null);
    setTestConsoleOutput('');
    apiClient.fetchPRDetails(taskId)
      .then((data) => {
        setPrDetails(data);
      })
      .catch((err) => {
        console.error(err);
        alert(err.message || 'Failed to load PR details.');
      })
      .finally(() => {
        setIsLoadingPRDetails(false);
      });
  }, []);

  useEffect(() => {
    if (selectedPRTask) {
      loadPRDetails(selectedPRTask.id);
    } else {
      setPrDetails(null);
    }
  }, [selectedPRTask, loadPRDetails]);

  const handlePRDecision = async (
    action: 'accept' | 'reject' | 'request_adjustment'
  ) => {
    if (!selectedPRTask) return;
    try {
      await apiClient.decidePRReview(selectedPRTask.id, action);
      setSelectedPRTask(null);
      loadProjectData();
      alert(`PR review successfully marked as: ${action.toUpperCase()}`);
    } catch (err: any) {
      alert(err.message || 'Failed to submit PR decision.');
    }
  };

  const handleRerunPRTests = async () => {
    if (!selectedPRTask) return;
    setIsRerunningTests(true);
    setTestConsoleOutput('Running tests in worktree sandbox...');
    try {
      const res = await apiClient.rerunTests(selectedPRTask.id);
      setTestConsoleOutput(
        `Command finished with exit code ${res.exit_code}\n\n` +
        `STDOUT:\n${res.stdout}\n\n` +
        `STDERR:\n${res.stderr}`
      );
    } catch (err: any) {
      setTestConsoleOutput(`Error running tests: ${err.message}`);
    } finally {
      setIsRerunningTests(false);
    }
  };

  const handleOpenPROrTaskFolder = async () => {
    if (!selectedPRTask) return;
    try {
      const res = await apiClient.openLocalPath(selectedPRTask.id);
      alert(`Opened folder: ${res.path}`);
    } catch (err: any) {
      alert(err.message || 'Failed to open local worktree folder.');
    }
  };

  useEffect(() => {
    if (editingTask) {
      setEditTitle(editingTask.title);
      setEditDesc(editingTask.description);
      setEditRisk(editingTask.risk_level || 'low');
      setEditCriteria(editingTask.acceptance_criteria?.join('\n') || '');
      setEditDeps(editingTask.dependency_task_ids?.join(', ') || '');
    }
  }, [editingTask]);

  const handleRemoveDependency = (depId: number) => {
    if (!editingTask) return;
    const updatedDeps = (editingTask.dependency_task_ids || []).filter(
      (id) => id !== depId
    );
    setEditingTask({
      ...editingTask,
      dependency_task_ids: updatedDeps,
    });
    setEditDeps(updatedDeps.join(', '));
  };

  const handleAddDependency = (depId: number) => {
    if (!editingTask) return;
    if (editingTask.id === depId) return;
    const currentDeps = editingTask.dependency_task_ids || [];
    if (currentDeps.includes(depId)) return;
    if (wouldCreateCycle(editingTask.id, [...currentDeps, depId], tasks)) {
      alert('Cannot add blocker: this would create a circular dependency cycle!');
      return;
    }
    const updatedDeps = [...currentDeps, depId];
    setEditingTask({
      ...editingTask,
      dependency_task_ids: updatedDeps,
    });
    setEditDeps(updatedDeps.join(', '));
  };

  const handleRemoveChildDependency = async (childTask: Task) => {
    if (!editingTask) return;
    try {
      const newDeps = (childTask.dependency_task_ids || []).filter(
        (id) => id !== editingTask.id
      );
      await apiClient.updateTask(childTask.id, {
        dependency_task_ids: newDeps,
      });
      setTasks((prev) =>
        prev.map((t) =>
          t.id === childTask.id ? { ...t, dependency_task_ids: newDeps } : t
        )
      );
    } catch (err: any) {
      alert(`Failed to remove child dependency: ${err.message}`);
    }
  };

  const handleAddChildDependency = async (childTaskId: number) => {
    if (!editingTask) return;
    const childTask = tasks.find((t) => t.id === childTaskId);
    if (!childTask) return;
    const currentDeps = childTask.dependency_task_ids || [];
    if (currentDeps.includes(editingTask.id)) return;
    if (
      wouldCreateCycle(
        childTask.id,
        [...currentDeps, editingTask.id],
        tasks
      )
    ) {
      alert('Cannot add dependency: this would create a circular dependency cycle!');
      return;
    }
    try {
      const newDeps = [...currentDeps, editingTask.id];
      await apiClient.updateTask(childTask.id, {
        dependency_task_ids: newDeps,
      });
      setTasks((prev) =>
        prev.map((t) =>
          t.id === childTask.id ? { ...t, dependency_task_ids: newDeps } : t
        )
      );
    } catch (err: any) {
      alert(`Failed to add child dependency: ${err.message}`);
    }
  };

  useEffect(() => {
    setBacklogPage(1);
    setMissionControlPage(1);
    setImportResult(null);
  }, [activeProject, activeEpic]);

  // Live SSE events
  const [events, setEvents] = useState<LifecycleEventPayload[]>([]);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const [pendingApprovals, setPendingApprovals] = useState<ActionApproval[]>([]);
  const [, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync hash routing
  useEffect(() => {
    const handleHash = () => {
      const hash = window.location.hash.replace('#/', '');
      const validTabs: Tab[] = [
        'mission-control',
        'prd-backlog',
        'agents',
        'runs',
        'prs',
        'worktrees',
        'models',
        'skills',
        'memory',
        'safety',
        'settings',
      ];
      if (validTabs.includes(hash as Tab)) {
        setCurrentTab(hash as Tab);
      }
    };
    window.addEventListener('hashchange', handleHash);
    handleHash();
    return () => window.removeEventListener('hashchange', handleHash);
  }, []);

  // Fetch initial projects
  useEffect(() => {
    setLoading(true);
    apiClient
      .fetchProjects()
      .then((data) => {
        setProjects(data);
        if (data.length > 0) {
          setActiveProject(data[0]);
        }
        setBackendHealthy(true);
      })
      .catch((err) => {
        setError('Failed to connect to LocalForge OS backend. Make sure the FastAPI server is running.');
        setBackendHealthy(false);
        console.error(err);
      })
      .finally(() => setLoading(false));
  }, []);

  // Check health periodically
  useEffect(() => {
    const checkHealth = () => {
      apiClient
        .fetchProjects()
        .then(() => setBackendHealthy(true))
        .catch(() => setBackendHealthy(false));
    };
    const interval = setInterval(checkHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  // Load project-specific data
  const loadProjectData = useCallback(() => {
    if (!activeProject) return;
    setLoading(true);
    Promise.all([
      apiClient.fetchTasks(activeProject.id),
      apiClient.fetchRuns(activeProject.id),
      apiClient.fetchAgents(),
      apiClient.fetchModels(),
      apiClient.fetchPolicy(activeProject.id, 'default').catch(() => null),
      apiClient.fetchPendingApprovals(activeProject.id).catch(() => []),
      apiClient.fetchEpics(activeProject.id).catch(() => []),
      apiClient.fetchModelRoutes(activeProject.id).catch(() => []),
      apiClient.fetchMemoryFacts(activeProject.id).catch(() => []),
      apiClient.fetchSkills(activeProject.id).catch(() => []),
      apiClient.fetchWorktrees(activeProject.id).catch(() => []),
      apiClient.fetchModelMetrics(activeProject.id).catch(() => []),
      apiClient.fetchChiefEngineerUsage(activeProject.id).catch(() => null),
      apiClient.fetchProjectSettings(activeProject.id).catch(() => null),
    ])
      .then(([
        tData,
        rData,
        aData,
        mData,
        pData,
        paData,
        eData,
        mrData,
        memData,
        skillsData,
        worktreeData,
        modelMetricData,
        chiefEngineerData,
        settingsData,
      ]) => {
        setTasks(tData);
        setRuns(rData);
        setAgents(aData);
        setModels(mData.models);
        setPolicy(pData);
        setPendingApprovals(paData);
        setEpics(eData);
        setModelRoutes(mrData);
        setRouteDrafts(
          Object.fromEntries(mrData.map((route) => [route.role, route]))
        );
        setProjectMemory(memData);
        setSkills(skillsData);
        setWorktrees(worktreeData);
        setModelMetrics(modelMetricData);
        setChiefEngineerUsage(chiefEngineerData);
        setProjectSettings(settingsData);
        setError(null);
      })
      .catch((err) => {
        console.error(err);
        setError('Error synchronizing database state with backend.');
      })
      .finally(() => setLoading(false));
  }, [activeProject]);

  useEffect(() => {
    loadProjectData();
  }, [loadProjectData]);

  // Load selected task artifacts
  useEffect(() => {
    if (!selectedTask) {
      setTaskArtifacts([]);
      setSelectedArtifactContent(null);
      return;
    }
    apiClient
      .fetchTaskArtifacts(selectedTask.id)
      .then((data) => setTaskArtifacts(data))
      .catch((err) => console.error(err));
  }, [selectedTask]);

  // SSE handler callback
  const handleLiveEvent = useCallback((event: LifecycleEventPayload) => {
    setEvents((prev) => [event, ...prev].slice(0, 50));
    // Reload state if task status changed or runs modified or approvals decided
    const reloadEvents = [
      'task.status_changed',
      'run.started',
      'safety.action_allowed',
      'safety.action_blocked',
      'safety.action_approved',
      'safety.action_rejected',
      'test.finished',
      'repair.started',
      'repair.succeeded',
      'repair.failed',
      'artifact.created',
      'agent.action_requested',
    ];
    if (reloadEvents.includes(event.event_type)) {
      loadProjectData();
    }
    if (selectedAgent) {
      apiClient
        .fetchAgentDetails(selectedAgent.id)
        .then((details) => {
          setAgentDetails(details);
        })
        .catch((err) => console.error('SSE reload agent details failed:', err));
    }
  }, [loadProjectData, selectedAgent]);

  // Subscribe to SSE
  const sseConnected = useProjectEvents(activeProject?.id || 0, handleLiveEvent);

  const triggerRunCommand = async (
    runId: number,
    action: 'start' | 'pause' | 'resume' | 'stop'
  ) => {
    try {
      await apiClient.commandRun(runId, action);
      loadProjectData();
    } catch (err: any) {
      alert(err.message || 'Failed to trigger run command.');
    }
  };

  const showArtifactContent = async (artId: number, path: string) => {
    try {
      const data = await apiClient.fetchArtifactContent(artId);
      setSelectedArtifactContent({ path, content: data.content });
    } catch (err: any) {
      alert(err.message || 'Failed to read artifact content.');
    }
  };

  const handleImportPRD = async () => {
    if (!activeProject) return;
    if (!prdPath.trim()) {
      alert('Please specify a PRD file path.');
      return;
    }
    try {
      setError(null);
      const res = await apiClient.importPRD(activeProject.id, prdPath, dryRun);
      setImportResult(res);
      loadProjectData();
    } catch (err: any) {
      alert(err.message || 'Failed to import PRD.');
    }
  };

  const handleUpdateTask = async (task: Task, fields: Partial<Task>) => {
    try {
      setError(null);
      await apiClient.updateTask(task.id, fields);
      setEditingTask(null);
      loadProjectData();
    } catch (err: any) {
      alert(err.message || 'Failed to update task.');
    }
  };

  const handleApproveTask = async (taskId: number) => {
    try {
      setError(null);
      await apiClient.approveTask(taskId);
      loadProjectData();
    } catch (err: any) {
      alert(err.message || 'Failed to approve task.');
    }
  };

  const taskColumns: Column<Task>[] = [
    {
      header: 'Key',
      accessor: (t) => (
        <span
          style={{ fontWeight: 600, color: 'var(--color-primary)', cursor: 'pointer' }}
          onClick={() => setSelectedTask(t)}
        >
          {t.key}
        </span>
      ),
      width: '100px',
    },
    {
      header: 'Title',
      accessor: (t) => (
        <span
          style={{ cursor: 'pointer', fontWeight: 500 }}
          onClick={() => setSelectedTask(t)}
        >
          {t.title}
        </span>
      ),
    },
    {
      header: 'Status',
      accessor: (t) => <StatusBadge status={t.status} />,
      width: '150px',
    },
  ];

  const runColumns: Column<Run>[] = [
    {
      header: 'ID',
      accessor: (r) => <span>Run #{r.id}</span>,
      width: '100px',
    },
    {
      header: 'Mode',
      accessor: (r) => <span style={{ textTransform: 'capitalize' }}>{r.mode}</span>,
    },
    {
      header: 'Initiator',
      accessor: (r) => <span>{r.initiated_by}</span>,
    },
    {
      header: 'Status',
      accessor: (r) => <StatusBadge status={r.status} />,
      width: '150px',
    },
    {
      header: 'Actions',
      accessor: (r) => (
        <div style={{ display: 'flex', gap: '8px' }}>
          {r.status === 'PENDING' && (
            <Button variant="success" onClick={() => triggerRunCommand(r.id, 'start')}>
              Start
            </Button>
          )}
          {r.status === 'RUNNING' && (
            <Button variant="warning" onClick={() => triggerRunCommand(r.id, 'pause')}>
              Pause
            </Button>
          )}
          {r.status === 'PAUSED' && (
            <Button variant="success" onClick={() => triggerRunCommand(r.id, 'resume')}>
              Resume
            </Button>
          )}
          {['RUNNING', 'PAUSED'].includes(r.status) && (
            <Button variant="danger" onClick={() => triggerRunCommand(r.id, 'stop')}>
              Stop
            </Button>
          )}
        </div>
      ),
      width: '250px',
    },
  ];



  const renderTabContent = () => {
    switch (currentTab) {
      case 'mission-control': {
        const activeRun =
          runs.find((r) => r.status === 'RUNNING' || r.status === 'PAUSED') ||
          runs[0];
        const lastEvent = events[0];

        const taskCounts = {
          total: tasks.length,
          ready: tasks.filter((t) => t.status === 'READY').length,
          active: tasks.filter((t) => [
            'CLAIMED', 'PLANNING', 'IMPLEMENTING', 'TESTING', 'REPAIRING', 'REVIEWING'
          ].includes(t.status)).length,
          blocked: tasks.filter((t) => t.status === 'BLOCKED').length,
          prReady: tasks.filter((t) => t.status === 'PR_READY').length,
          done: tasks.filter((t) => t.status === 'DONE').length,
        };

        const handleDecision = async (id: number, action: 'approve' | 'reject') => {
          try {
            await apiClient.decideApproval(id, action);
            loadProjectData();
          } catch (err: any) {
            alert(err.message || 'Failed to submit decision.');
          }
        };

        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
              <div style={{ flex: 2, minWidth: '400px' }}>
                <Card
                  title={activeRun ? `Current Execution: Run #${activeRun.id}` : 'No Active Run'}
                  actions={
                    activeRun && (
                      <div style={{ display: 'flex', gap: '8px' }}>
                        {activeRun.status === 'PENDING' && (
                          <Button variant="success" onClick={() => triggerRunCommand(activeRun.id, 'start')}>
                            Start
                          </Button>
                        )}
                        {activeRun.status === 'RUNNING' && (
                          <Button variant="warning" onClick={() => triggerRunCommand(activeRun.id, 'pause')}>
                            Pause
                          </Button>
                        )}
                        {activeRun.status === 'PAUSED' && (
                          <Button variant="success" onClick={() => triggerRunCommand(activeRun.id, 'resume')}>
                            Resume
                          </Button>
                        )}
                        {['RUNNING', 'PAUSED'].includes(activeRun.status) && (
                          <Button variant="danger" onClick={() => triggerRunCommand(activeRun.id, 'stop')}>
                            Stop
                          </Button>
                        )}
                      </div>
                    )
                  }
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    {activeRun ? (
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <span style={{ color: 'var(--text-muted)', fontSize: '12px', display: 'block' }}>MODE</span>
                          <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{activeRun.mode}</span>
                        </div>
                        <div>
                          <span style={{ color: 'var(--text-muted)', fontSize: '12px', display: 'block' }}>INITIATOR</span>
                          <span>{activeRun.initiated_by}</span>
                        </div>
                        <div>
                          <span style={{ color: 'var(--text-muted)', fontSize: '12px', display: 'block' }}>STATUS</span>
                          <StatusBadge status={activeRun.status} />
                        </div>
                      </div>
                    ) : (
                      <p style={{ color: 'var(--text-secondary)' }}>No runs are currently active or pending.</p>
                    )}

                    <div style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(80px, 1fr))',
                      gap: '12px',
                      borderTop: '1px solid var(--border-color)',
                      borderBottom: '1px solid var(--border-color)',
                      padding: '16px 0',
                    }}>
                      {[
                        { label: 'Total', count: taskCounts.total, color: 'var(--text-primary)' },
                        { label: 'Ready', count: taskCounts.ready, color: 'var(--color-primary)' },
                        { label: 'Active', count: taskCounts.active, color: 'var(--color-info)' },
                        { label: 'Blocked', count: taskCounts.blocked, color: 'var(--color-blocked)' },
                        { label: 'PR Ready', count: taskCounts.prReady, color: 'var(--color-success)' },
                        { label: 'Done', count: taskCounts.done, color: 'var(--color-success)' },
                      ].map((cell) => (
                        <div key={cell.label} style={{ textAlign: 'center' }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block' }}>
                            {cell.label}
                          </span>
                          <span style={{ fontSize: '20px', fontWeight: 700, color: cell.color }}>
                            {cell.count}
                          </span>
                        </div>
                      ))}
                    </div>

                    <div>
                      <span style={{ color: 'var(--text-muted)', fontSize: '12px', display: 'block', marginBottom: '4px' }}>
                        LAST EVENT
                      </span>
                      {lastEvent ? (
                        <div style={{
                          padding: '10px 12px',
                          borderRadius: '6px',
                          background: 'rgba(255,255,255,0.02)',
                          border: '1px solid var(--border-color)',
                          fontSize: '13px',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                        }}>
                          <span style={{ fontWeight: 600, color: 'var(--color-primary)' }}>{lastEvent.event_type}</span>
                          <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>
                            {lastEvent.payload.action || lastEvent.payload.status || 'system alert'}
                          </span>
                        </div>
                      ) : (
                        <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No events streamed yet.</p>
                      )}
                    </div>
                  </div>
                </Card>
              </div>

              <div style={{ flex: 1, minWidth: '300px' }}>
                <Card title="Risk & Safety Approvals">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {pendingApprovals.length === 0 && (
                      <EmptyState
                        title="Safe Operations"
                        message="No pending safety manual approvals or policy blocks requiring human intervention."
                      />
                    )}

                    {pendingApprovals.map((app) => (
                      <div
                        key={app.id}
                        style={{
                          padding: '14px',
                          borderRadius: '8px',
                          border: '1px solid hsla(38, 92%, 50%, 0.3)',
                          backgroundColor: 'hsla(38, 92%, 50%, 0.08)',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '10px',
                        }}
                      >
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{
                              fontWeight: 700,
                              color: 'var(--color-warning)',
                              fontSize: '12px',
                              textTransform: 'uppercase',
                            }}>
                              {app.kind} REQUIRED
                            </span>
                            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                              Run #{app.run_id}
                            </span>
                          </div>
                          <p style={{ fontSize: '13px', marginTop: '4px', fontFamily: 'monospace' }}>
                            {app.payload.cmd || app.payload.path || 'Access request'}
                          </p>
                        </div>
                        <div style={{ display: 'flex', gap: '8px', alignSelf: 'flex-end' }}>
                          <Button variant="success" onClick={() => handleDecision(app.id, 'approve')}>
                            Approve
                          </Button>
                          <Button variant="danger" onClick={() => handleDecision(app.id, 'reject')}>
                            Reject
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              </div>
            </div>

            <div>
              <Card title="Agent Fleet Status">
                {agents.length === 0 ? (
                  <EmptyState title="No Active Agents" message="No autonomous agents are currently active in this run." />
                ) : (
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                    gap: '16px',
                  }}>
                    {agents.map((agent) => (
                      <div
                        key={agent.id}
                        style={{
                          padding: '16px',
                          borderRadius: '8px',
                          border: '1px solid var(--border-color)',
                          background: 'rgba(255,255,255,0.02)',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '12px',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontWeight: 600 }}>{agent.name}</span>
                          <StatusBadge status={agent.status} />
                        </div>
                        <div>
                          <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block' }}>ROLE</span>
                          <span style={{ fontSize: '14px', textTransform: 'capitalize' }}>{agent.role}</span>
                        </div>
                        {agent.current_task_run_id ? (
                          <div>
                            <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block' }}>ACTIVE TASK</span>
                            <span style={{ fontSize: '13px', color: 'var(--color-primary)' }}>
                              Task Run #{agent.current_task_run_id}
                            </span>
                          </div>
                        ) : (
                          <div>
                            <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block' }}>ACTIVITY</span>
                            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Idle / Scanning</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </div>

            <div style={{ display: 'flex', gap: '24px', alignItems: 'stretch' }}>
              <div style={{ flex: 2, display: 'flex', flexDirection: 'column', gap: '24px' }}>
                <Card title="Project Backlog Tasks">
                  {(() => {
                    const mcPageSize = 5;
                    const mcTotalPages = Math.ceil(tasks.length / mcPageSize) || 1;
                    const mcPaginatedTasks = tasks.slice(
                      (missionControlPage - 1) * mcPageSize,
                      missionControlPage * mcPageSize
                    );
                    return (
                      <>
                        <Table
                          columns={taskColumns}
                          data={mcPaginatedTasks}
                          emptyMessage="No tasks found for this project."
                        />
                        <div style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginTop: '16px',
                          borderTop: '1px solid var(--border-color)',
                          paddingTop: '16px',
                        }}>
                          <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                            Page {missionControlPage} of {mcTotalPages} ({tasks.length} tasks)
                          </span>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <Button
                              variant="ghost"
                              disabled={missionControlPage <= 1}
                              onClick={() => setMissionControlPage((p) => Math.max(p - 1, 1))}
                            >
                              Previous
                            </Button>
                            <Button
                              variant="ghost"
                              disabled={missionControlPage >= mcTotalPages}
                              onClick={() =>
                                setMissionControlPage((p) => Math.min(p + 1, mcTotalPages))
                              }
                            >
                              Next
                            </Button>
                          </div>
                        </div>
                      </>
                    );
                  })()}
                </Card>
              </div>

              {selectedTask && (
                <div style={{ flex: 1 }}>
                  <Card
                    title={`Task details: ${selectedTask.key}`}
                    actions={
                      <Button variant="ghost" onClick={() => setSelectedTask(null)}>
                        Close
                      </Button>
                    }
                  >
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      <div>
                        <h4 style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>TITLE</h4>
                        <p style={{ fontWeight: 500 }}>{selectedTask.title}</p>
                      </div>
                      <div>
                        <h4 style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>STATUS</h4>
                        <StatusBadge status={selectedTask.status} />
                      </div>
                      <div>
                        <h4 style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>DESCRIPTION</h4>
                        <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
                          {selectedTask.description || 'No description provided.'}
                        </p>
                      </div>

                      <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
                        <h4 style={{ marginBottom: '8px', fontSize: '14px' }}>Generated Artifacts</h4>
                        {taskArtifacts.length === 0 ? (
                          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                            No artifacts emitted yet.
                          </p>
                        ) : (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {taskArtifacts.map((art) => (
                              <div
                                key={art.id}
                                onClick={() => showArtifactContent(art.id, art.path)}
                                style={{
                                  padding: '8px 12px',
                                  borderRadius: '6px',
                                  border: '1px solid var(--border-color)',
                                  background: 'rgba(255,255,255,0.02)',
                                  fontSize: '13px',
                                  cursor: 'pointer',
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  alignItems: 'center',
                                }}
                              >
                                <span>{art.path.split('/').pop()}</span>
                                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                                  {art.type}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </Card>
                </div>
              )}
            </div>

            {selectedArtifactContent && (
              <Card
                title={`File: ${selectedArtifactContent.path}`}
                actions={
                  <Button variant="ghost" onClick={() => setSelectedArtifactContent(null)}>
                    Clear File
                  </Button>
                }
              >
                <CodeBlock code={selectedArtifactContent.content} />
              </Card>
            )}
          </div>
        );
      }

      case 'prd-backlog': {
        const filteredTasks = activeEpic
          ? tasks.filter((t) => t.epic_id === activeEpic.id)
          : tasks;

        const depsList = editDeps
          .split(',')
          .map((d) => parseInt(d.trim(), 10))
          .filter((d) => !isNaN(d));

        const validationError = (() => {
          if (!editTitle.trim()) return 'Title is required.';
          if (!editDesc.trim()) return 'Description is required.';
          if (editingTask && wouldCreateCycle(editingTask.id, depsList, tasks)) {
            return 'Cyclic dependency loop detected! A task cannot depend on its descendants.';
          }
          return null;
        })();

        const onSaveTask = () => {
          if (validationError) return;
          if (!editingTask) return;
          const criteriaList = editCriteria
            .split('\n')
            .map((c) => c.trim())
            .filter((c) => c.length > 0);

          handleUpdateTask(editingTask, {
            title: editTitle,
            description: editDesc,
            risk_level: editRisk,
            acceptance_criteria: criteriaList,
            dependency_task_ids: depsList,
          });
        };

        const getRiskColor = (level?: string) => {
          if (level === 'high') return 'var(--color-danger)';
          if (level === 'medium') return 'var(--color-warning)';
          return 'rgba(255, 255, 255, 0.1)';
        };

        const getRiskTextColor = (level?: string) => {
          if (level === 'high' || level === 'medium') return '#000';
          return 'inherit';
        };

        const isAllSelected = activeEpic === null;

        // Paginate tasks list
        const pageSize = 5;
        const totalPages = Math.ceil(filteredTasks.length / pageSize) || 1;
        const paginatedTasks = filteredTasks.slice(
          (backlogPage - 1) * pageSize,
          backlogPage * pageSize
        );

        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            {/* PRD Importer Panel */}
            <Card title="PRD Compiler & Importer">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
                  Analyze specification Markdown documents to extract project epics,
                  user stories, sizing heuristics, and dependencies.
                </p>
                <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                  <input
                    type="text"
                    placeholder="e.g. docs/LocalForge_OS_PRD.md"
                    value={prdPath}
                    onChange={(e) => setPrdPath(e.target.value)}
                    style={{
                      flex: 1,
                      padding: '10px 12px',
                      borderRadius: '8px',
                      backgroundColor: 'var(--bg-input)',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-primary)',
                      outline: 'none',
                    }}
                  />
                  <label style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    cursor: 'pointer',
                  }}>
                    <input
                      type="checkbox"
                      checked={dryRun}
                      onChange={(e) => setDryRun(e.target.checked)}
                      style={{ cursor: 'pointer' }}
                    />
                    <span style={{ fontSize: '13px' }}>Dry Run</span>
                  </label>
                  <Button variant="success" onClick={handleImportPRD}>
                    Compile & Import
                  </Button>
                </div>

                {importResult && (
                  <div style={{
                    padding: '16px',
                    borderRadius: '8px',
                    border: '1px solid var(--color-success)',
                    background: 'rgba(46, 125, 50, 0.08)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                  }}>
                    <h4 style={{ color: 'var(--color-success)', fontWeight: 600 }}>
                      PRD compiled successfully!
                    </h4>
                    <p style={{ fontSize: '13px', margin: 0, lineHeight: '1.6' }}>
                      <strong>Document Hash:</strong> {importResult.document_hash} <br />
                      <strong>Persisted:</strong> {importResult.persisted ? 'Yes' : 'No'} <br />
                      <strong>Epics Created:</strong> {importResult.epics_created} <br />
                      <strong>Tasks Created:</strong> {importResult.tasks_created}
                    </p>
                  </div>
                )}
              </div>
            </Card>

            <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
              {/* Epics Map List */}
              <div style={{ flex: 1, minWidth: '250px' }}>
                <Card title="Epics Map">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <div
                      onClick={() => setActiveEpic(null)}
                      style={{
                        padding: '12px',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        backgroundColor: isAllSelected
                          ? 'var(--color-primary)'
                          : 'rgba(255, 255, 255, 0.02)',
                        border: '1px solid var(--border-color)',
                        fontWeight: isAllSelected ? 600 : 500,
                        color: isAllSelected ? '#fff' : 'var(--text-primary)',
                      }}
                    >
                      All Project Tasks
                    </div>
                    {epics.length === 0 && (
                      <p style={{
                        fontSize: '13px',
                        color: 'var(--text-muted)',
                        padding: '8px',
                      }}>
                        No epics loaded. Import a PRD to begin.
                      </p>
                    )}
                    {epics.map((epic) => {
                      const isSelected = activeEpic?.id === epic.id;
                      return (
                        <div
                          key={epic.id}
                          onClick={() => setActiveEpic(epic)}
                          style={{
                            padding: '12px',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            backgroundColor: isSelected
                              ? 'var(--color-primary)'
                              : 'rgba(255, 255, 255, 0.02)',
                            border: '1px solid var(--border-color)',
                            fontWeight: isSelected ? 600 : 500,
                            color: isSelected ? '#fff' : 'var(--text-primary)',
                          }}
                        >
                          <div style={{ fontWeight: 600, fontSize: '14px' }}>
                            {epic.title}
                          </div>
                          <div style={{
                            fontSize: '11px',
                            color: isSelected
                              ? 'rgba(255,255,255,0.7)'
                              : 'var(--text-muted)',
                            marginTop: '4px',
                          }}>
                            {epic.summary.length > 50
                              ? epic.summary.slice(0, 50) + '...'
                              : epic.summary}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Card>
              </div>

              {/* Tasks List */}
              <div style={{
                flex: 2,
                minWidth: '400px',
                display: 'flex',
                flexDirection: 'column',
                gap: '24px',
              }}>
                <Card
                  title={activeEpic ? `Epic: ${activeEpic.title}` : 'All Project Tasks'}
                >
                  {paginatedTasks.length === 0 ? (
                    <EmptyState
                      title="No Tasks"
                      message="No tasks generated under this view."
                    />
                  ) : (
                    <>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        {paginatedTasks.map((t) => (
                          <div
                            key={t.id}
                            style={{
                              padding: '16px',
                              borderRadius: '8px',
                              border: '1px solid var(--border-color)',
                              backgroundColor: 'rgba(255, 255, 255, 0.01)',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                            }}
                          >
                            <div style={{ flex: 1, marginRight: '16px' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{
                                  fontWeight: 700,
                                  color: 'var(--color-primary)',
                                }}>{t.key}</span>
                                <span style={{ fontWeight: 600 }}>{t.title}</span>
                              </div>
                              <p style={{
                                fontSize: '13px',
                                color: 'var(--text-muted)',
                                marginTop: '6px',
                                lineHeight: '1.4',
                              }}>
                                {t.description}
                              </p>
                              <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                                <StatusBadge status={t.status} />
                                {t.risk_level && (
                                  <span style={{
                                    fontSize: '11px',
                                    padding: '2px 6px',
                                    borderRadius: '4px',
                                    fontWeight: 600,
                                    textTransform: 'uppercase',
                                    backgroundColor: getRiskColor(t.risk_level),
                                    color: getRiskTextColor(t.risk_level),
                                  }}>
                                    {t.risk_level} risk
                                  </span>
                                )}
                                {t.dependency_task_ids && t.dependency_task_ids.length > 0 && (
                                  <span style={{
                                    fontSize: '11px',
                                    padding: '2px 6px',
                                    borderRadius: '4px',
                                    fontWeight: 500,
                                    backgroundColor: 'rgba(255, 255, 255, 0.05)',
                                    color: 'var(--text-muted)',
                                  }}>
                                    Deps: {t.dependency_task_ids.join(', ')}
                                  </span>
                                )}
                              </div>
                            </div>

                            <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                              {t.status === 'BACKLOG' && (
                                <Button variant="success" onClick={() => handleApproveTask(t.id)}>
                                  Approve Plan
                                </Button>
                              )}
                              <Button variant="ghost" onClick={() => setEditingTask(t)}>
                                Edit
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Pagination Controls */}
                      <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginTop: '16px',
                        borderTop: '1px solid var(--border-color)',
                        paddingTop: '16px',
                      }}>
                        <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                          Page {backlogPage} of {totalPages} ({filteredTasks.length} tasks)
                        </span>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <Button
                            variant="ghost"
                            disabled={backlogPage <= 1}
                            onClick={() => setBacklogPage((p) => Math.max(p - 1, 1))}
                          >
                            Previous
                          </Button>
                          <Button
                            variant="ghost"
                            disabled={backlogPage >= totalPages}
                            onClick={() => setBacklogPage((p) => Math.min(p + 1, totalPages))}
                          >
                            Next
                          </Button>
                        </div>
                      </div>
                    </>
                  )}
                </Card>

                {/* Task Editor Form */}
                {editingTask && (
                  <Card
                    title={`Edit Task: ${editingTask.key}`}
                    actions={
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <Button variant="ghost" onClick={() => setEditingTask(null)}>
                          Cancel
                        </Button>
                        <Button
                          variant="success"
                          disabled={!!validationError}
                          onClick={onSaveTask}
                        >
                          Save Changes
                        </Button>
                      </div>
                    }
                  >
                    {validationError && (
                      <div style={{
                        color: 'var(--color-danger)',
                        fontSize: '13px',
                        fontWeight: 600,
                        padding: '8px 12px',
                        borderRadius: '6px',
                        backgroundColor: 'rgba(239, 83, 80, 0.08)',
                        border: '1px solid var(--color-danger)',
                        marginBottom: '16px',
                      }}>
                        ⚠️ {validationError}
                      </div>
                    )}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                      <div>
                        <label style={{
                          display: 'block',
                          fontSize: '11px',
                          fontWeight: 600,
                          color: 'var(--text-muted)',
                          marginBottom: '6px',
                        }}>
                          TITLE
                        </label>
                        <input
                          type="text"
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                          style={{
                            width: '100%',
                            padding: '10px',
                            borderRadius: '8px',
                            backgroundColor: 'var(--bg-input)',
                            border: '1px solid var(--border-color)',
                            color: 'var(--text-primary)',
                            outline: 'none',
                          }}
                        />
                      </div>

                      <div>
                        <label style={{
                          display: 'block',
                          fontSize: '11px',
                          fontWeight: 600,
                          color: 'var(--text-muted)',
                          marginBottom: '6px',
                        }}>
                          DESCRIPTION
                        </label>
                        <textarea
                          rows={4}
                          value={editDesc}
                          onChange={(e) => setEditDesc(e.target.value)}
                          style={{
                            width: '100%',
                            padding: '10px',
                            borderRadius: '8px',
                            backgroundColor: 'var(--bg-input)',
                            border: '1px solid var(--border-color)',
                            color: 'var(--text-primary)',
                            outline: 'none',
                            resize: 'vertical',
                          }}
                        />
                      </div>

                      <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                        <div style={{ flex: 1, minWidth: '150px' }}>
                          <label style={{
                            display: 'block',
                            fontSize: '11px',
                            fontWeight: 600,
                            color: 'var(--text-muted)',
                            marginBottom: '6px',
                          }}>
                            RISK LEVEL
                          </label>
                          <select
                            value={editRisk}
                            onChange={(e) => setEditRisk(e.target.value)}
                            style={{
                              width: '100%',
                              padding: '10px',
                              borderRadius: '8px',
                              backgroundColor: 'var(--bg-input)',
                              border: '1px solid var(--border-color)',
                              color: 'var(--text-primary)',
                              outline: 'none',
                              cursor: 'pointer',
                            }}
                          >
                            <option value="low">Low</option>
                            <option value="medium">Medium</option>
                            <option value="high">High</option>
                          </select>
                        </div>

                        <div style={{ flex: 1, minWidth: '150px' }}>
                          <label style={{
                            display: 'block',
                            fontSize: '11px',
                            fontWeight: 600,
                            color: 'var(--text-muted)',
                            marginBottom: '6px',
                          }}>
                            DEPENDENCIES (COMMA-SEPARATED TASK IDS)
                          </label>
                          <input
                            type="text"
                            placeholder="e.g. 1, 2, 3"
                            value={editDeps}
                            onChange={(e) => setEditDeps(e.target.value)}
                            style={{
                              width: '100%',
                              padding: '10px',
                              borderRadius: '8px',
                              backgroundColor: 'var(--bg-input)',
                              border: '1px solid var(--border-color)',
                              color: 'var(--text-primary)',
                              outline: 'none',
                            }}
                          />
                        </div>
                      </div>

                      <div>
                        <label style={{
                          display: 'block',
                          fontSize: '11px',
                          fontWeight: 600,
                          color: 'var(--text-muted)',
                          marginBottom: '6px',
                        }}>
                          ACCEPTANCE CRITERIA (ONE PER LINE)
                        </label>
                        <textarea
                          rows={4}
                          value={editCriteria}
                          onChange={(e) => setEditCriteria(e.target.value)}
                          style={{
                            width: '100%',
                            padding: '10px',
                            borderRadius: '8px',
                            backgroundColor: 'var(--bg-input)',
                            border: '1px solid var(--border-color)',
                            color: 'var(--text-primary)',
                            outline: 'none',
                            resize: 'vertical',
                          }}
                        />
                      </div>

                      {/* Visual DAG / Dependency Tree */}
                      <div style={{
                        marginTop: '20px',
                        borderTop: '1px solid var(--border-color)',
                        paddingTop: '20px',
                      }}>
                        <h4 style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          color: 'var(--text-muted)',
                          marginBottom: '12px',
                          textTransform: 'uppercase',
                          letterSpacing: '0.5px'
                        }}>
                          Task Dependency Tree
                        </h4>

                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '16px',
                          backgroundColor: 'rgba(255,255,255,0.01)',
                          padding: '16px',
                          borderRadius: '8px',
                          border: '1px solid var(--border-color)',
                        }}>
                          {/* Blockers Column */}
                          <div style={{
                            flex: 1,
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '8px',
                            alignItems: 'flex-end',
                          }}>
                            <span style={{
                              fontSize: '10px',
                              color: 'var(--text-muted)',
                              fontWeight: 600
                            }}>
                              BLOCKERS (PARENTS)
                            </span>
                            {tasks.filter(
                              t => editingTask.dependency_task_ids?.includes(t.id)
                            ).length === 0 ? (
                              <span style={{
                                fontSize: '12px',
                                color: 'var(--text-muted)',
                                fontStyle: 'italic'
                              }}>
                                None
                              </span>
                            ) : (
                              tasks
                                .filter(t => editingTask.dependency_task_ids?.includes(t.id))
                                .map(t => (
                                  <div
                                    key={t.id}
                                    style={{
                                      padding: '6px 10px',
                                      borderRadius: '6px',
                                      border: '1px solid var(--border-color)',
                                      backgroundColor: 'var(--bg-card)',
                                      fontSize: '12px',
                                      display: 'flex',
                                      alignItems: 'center',
                                      gap: '8px',
                                      maxWidth: '220px',
                                    }}
                                    title={`${t.key}: ${t.title}`}
                                  >
                                    <span style={{
                                      textOverflow: 'ellipsis',
                                      overflow: 'hidden',
                                      whiteSpace: 'nowrap',
                                    }}>
                                      <strong style={{
                                        color: 'var(--color-danger)',
                                        marginRight: '4px'
                                      }}>
                                        {t.key}
                                      </strong>
                                      {t.title}
                                    </span>
                                    <button
                                      onClick={() => handleRemoveDependency(t.id)}
                                      style={{
                                        background: 'none',
                                        border: 'none',
                                        color: 'var(--color-danger)',
                                        cursor: 'pointer',
                                        fontSize: '12px',
                                        padding: '0 2px',
                                        fontWeight: 700,
                                      }}
                                    >
                                      ✖
                                    </button>
                                  </div>
                                ))
                            )}

                            {/* Dropdown to add blocker */}
                            <select
                              onChange={(e) => {
                                if (e.target.value) {
                                  handleAddDependency(Number(e.target.value));
                                  e.target.value = '';
                                }
                              }}
                              style={{
                                padding: '4px 8px',
                                borderRadius: '4px',
                                border: '1px solid var(--border-color)',
                                backgroundColor: 'var(--bg-input)',
                                color: 'var(--text-secondary)',
                                fontSize: '11px',
                                marginTop: '4px',
                                maxWidth: '180px',
                              }}
                              defaultValue=""
                            >
                              <option value="" disabled>+ Add blocker...</option>
                              {tasks
                                .filter((t) => {
                                  if (t.id === editingTask.id) return false;
                                  if (editingTask.dependency_task_ids?.includes(t.id)) return false;
                                  if (wouldCreateCycle(
                                    editingTask.id,
                                    [...(editingTask.dependency_task_ids || []), t.id],
                                    tasks
                                  )) return false;
                                  return true;
                                })
                                .map((t) => (
                                  <option key={t.id} value={t.id}>
                                    {t.key}: {t.title}
                                  </option>
                                ))}
                            </select>
                          </div>

                          {/* Arrow connection */}
                          <div style={{ color: 'var(--text-muted)', fontSize: '18px', marginTop: '20px' }}>
                            ➔
                          </div>

                          {/* Current Node */}
                          <div style={{
                            padding: '10px 14px',
                            borderRadius: '8px',
                            border: '2px solid var(--color-primary)',
                            backgroundColor: 'rgba(74, 144, 226, 0.08)',
                            textAlign: 'center',
                            fontWeight: 600,
                            fontSize: '13px',
                            minWidth: '120px',
                            maxWidth: '200px',
                            boxShadow: '0 0 10px rgba(74, 144, 226, 0.2)',
                            marginTop: '10px',
                          }}>
                            <span style={{
                              display: 'block',
                              fontSize: '10px',
                              color: 'var(--text-muted)'
                            }}>
                              CURRENT TASK
                            </span>
                            <span style={{ color: 'var(--color-primary)' }}>
                              {editingTask.key}
                            </span>
                          </div>

                          {/* Arrow connection */}
                          <div style={{ color: 'var(--text-muted)', fontSize: '18px', marginTop: '20px' }}>
                            ➔
                          </div>

                          {/* Blocked Column */}
                          <div style={{
                            flex: 1,
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '8px',
                            alignItems: 'flex-start',
                          }}>
                            <span style={{
                              fontSize: '10px',
                              color: 'var(--text-muted)',
                              fontWeight: 600
                            }}>
                              BLOCKED TASKS (CHILDREN)
                            </span>
                            {tasks.filter(
                              t => t.dependency_task_ids?.includes(editingTask.id)
                            ).length === 0 ? (
                              <span style={{
                                fontSize: '12px',
                                color: 'var(--text-muted)',
                                fontStyle: 'italic'
                              }}>
                                None
                              </span>
                            ) : (
                              tasks
                                .filter(t => t.dependency_task_ids?.includes(editingTask.id))
                                .map(t => (
                                  <div
                                    key={t.id}
                                    style={{
                                      padding: '6px 10px',
                                      borderRadius: '6px',
                                      border: '1px solid var(--border-color)',
                                      backgroundColor: 'var(--bg-card)',
                                      fontSize: '12px',
                                      display: 'flex',
                                      alignItems: 'center',
                                      gap: '8px',
                                      maxWidth: '220px',
                                    }}
                                    title={`${t.key}: ${t.title}`}
                                  >
                                    <span style={{
                                      textOverflow: 'ellipsis',
                                      overflow: 'hidden',
                                      whiteSpace: 'nowrap',
                                    }}>
                                      <strong style={{
                                        color: 'var(--color-success)',
                                        marginRight: '4px'
                                      }}>
                                        {t.key}
                                      </strong>
                                      {t.title}
                                    </span>
                                    <button
                                      onClick={() => handleRemoveChildDependency(t)}
                                      style={{
                                        background: 'none',
                                        border: 'none',
                                        color: 'var(--color-danger)',
                                        cursor: 'pointer',
                                        fontSize: '12px',
                                        padding: '0 2px',
                                        fontWeight: 700,
                                      }}
                                    >
                                      ✖
                                    </button>
                                  </div>
                                ))
                            )}

                            {/* Dropdown to add child dependency */}
                            <select
                              onChange={(e) => {
                                if (e.target.value) {
                                  handleAddChildDependency(Number(e.target.value));
                                  e.target.value = '';
                                }
                              }}
                              style={{
                                padding: '4px 8px',
                                borderRadius: '4px',
                                border: '1px solid var(--border-color)',
                                backgroundColor: 'var(--bg-input)',
                                color: 'var(--text-secondary)',
                                fontSize: '11px',
                                marginTop: '4px',
                                maxWidth: '180px',
                              }}
                              defaultValue=""
                            >
                              <option value="" disabled>+ Add blocked...</option>
                              {tasks
                                .filter((t) => {
                                  if (t.id === editingTask.id) return false;
                                  if (t.dependency_task_ids?.includes(editingTask.id)) return false;
                                  if (wouldCreateCycle(
                                    t.id,
                                    [...(t.dependency_task_ids || []), editingTask.id],
                                    tasks
                                  )) return false;
                                  return true;
                                })
                                .map((t) => (
                                  <option key={t.id} value={t.id}>
                                    {t.key}: {t.title}
                                  </option>
                                ))}
                            </select>
                          </div>
                        </div>
                      </div>
                    </div>
                  </Card>
                )}
              </div>
            </div>
          </div>
        );
      }

      case 'agents':
        return (
          <div style={{
            display: 'flex',
            gap: '24px',
            height: 'calc(100vh - 120px)',
            overflow: 'hidden'
          }}>
            {/* Left Column: Agent Cards List */}
            <div style={{
              width: '350px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
              overflowY: 'auto',
              paddingRight: '4px'
            }}>
              <h3 style={{
                margin: 0,
                fontSize: '18px',
                fontWeight: 700,
                color: 'var(--text-primary)'
              }}>
                Active Coding Agents
              </h3>
              {agents.length === 0 ? (
                <EmptyState
                  title="No Active Agents"
                  message="No autonomous agents are currently active in this project."
                />
              ) : (
                agents.map((agent) => {
                  const isSelected = selectedAgent?.id === agent.id;
                  return (
                    <div
                      key={agent.id}
                      onClick={() => setSelectedAgent(agent)}
                      style={{
                        padding: '16px',
                        borderRadius: '12px',
                        border: isSelected
                          ? '1px solid var(--color-primary)'
                          : '1px solid var(--border-color)',
                        backgroundColor: isSelected
                          ? 'rgba(33, 150, 243, 0.08)'
                          : 'rgba(255, 255, 255, 0.02)',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease',
                        boxShadow: isSelected
                          ? '0 4px 12px rgba(33, 150, 243, 0.15)'
                          : 'none',
                      }}
                    >
                      <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: '8px'
                      }}>
                        <span style={{
                          fontWeight: 700,
                          fontSize: '15px',
                          color: 'var(--text-primary)'
                        }}>
                          {agent.name}
                        </span>
                        <StatusBadge status={agent.status} />
                      </div>
                      <div style={{
                        fontSize: '13px',
                        color: 'var(--text-secondary)',
                        marginBottom: '4px',
                        textTransform: 'capitalize'
                      }}>
                        <strong>Role:</strong> {agent.role}
                      </div>
                      <div style={{
                        fontSize: '12px',
                        color: 'var(--text-muted)',
                        fontFamily: 'monospace'
                      }}>
                        {agent.model_profile_id || 'default-model'}
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Right Column: Agent Details & Control panel */}
            <div style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              gap: '20px',
              overflowY: 'auto',
              borderLeft: '1px solid var(--border-color)',
              paddingLeft: '24px'
            }}>
              {!selectedAgent ? (
                <EmptyState
                  title="No Agent Selected"
                  message="Select an active coding agent to view runtime details and control execution."
                />
              ) : isLoadingAgentDetails ? (
                <div style={{
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'center',
                  height: '100%'
                }}>
                  <div style={{ color: 'var(--text-secondary)' }}>Loading agent details...</div>
                </div>
              ) : !agentDetails ? (
                <div style={{
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'center',
                  height: '100%'
                }}>
                  <div style={{ color: 'var(--text-secondary)' }}>Failed to load agent details.</div>
                </div>
              ) : (
                <>
                  {/* Agent Header Info */}
                  <Card title={`Agent: ${agentDetails.agent.name}`}>
                    <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
                      <div style={{ flex: 1, minWidth: '150px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block' }}>
                          ROLE & PROFILE
                        </span>
                        <span style={{ fontSize: '14px', fontWeight: 600, textTransform: 'capitalize' }}>
                          {agentDetails.agent.role}
                        </span>
                      </div>
                      <div style={{ flex: 1, minWidth: '150px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block' }}>
                          LLM MODEL
                        </span>
                        <span style={{ fontSize: '13px', fontFamily: 'monospace' }}>
                          {agentDetails.agent.model_profile_id || 'gemini-2.5-pro'}
                        </span>
                      </div>
                      <div style={{ flex: 1, minWidth: '150px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block' }}>
                          STATUS & CONCURRENCY
                        </span>
                        <span style={{ fontSize: '14px', fontWeight: 600 }}>
                          {agentDetails.agent.status} (Max {agentDetails.agent.max_concurrent_tasks || 1} task)
                        </span>
                      </div>
                    </div>
                  </Card>

                  {/* Active Task Run Context and Control Panel */}
                  {agentDetails.current_task ? (
                    <Card title={`Active Task Run: ${agentDetails.current_task.key}`}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <div>
                          <strong style={{ fontSize: '15px', display: 'block', marginBottom: '4px' }}>
                            {agentDetails.current_task.title}
                          </strong>
                          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: 0 }}>
                            {agentDetails.current_task.description}
                          </p>
                        </div>

                        <div style={{ display: 'flex', gap: '16px', fontSize: '13px' }}>
                          <div>
                            <span style={{ color: 'var(--text-muted)', marginRight: '6px' }}>Task Status:</span>
                            <strong style={{ color: 'var(--color-primary)' }}>
                              {agentDetails.current_task.status}
                            </strong>
                          </div>
                          {agentDetails.latest_run && (
                            <>
                              <div>
                                <span style={{ color: 'var(--text-muted)', marginRight: '6px' }}>Run Status:</span>
                                <strong>{agentDetails.latest_run.status}</strong>
                              </div>
                              <div>
                                <span style={{ color: 'var(--text-muted)', marginRight: '6px' }}>Attempt:</span>
                                <strong>{agentDetails.latest_run.attempt_count}</strong>
                              </div>
                            </>
                          )}
                        </div>

                        {/* Control Actions */}
                        <div style={{
                          display: 'flex',
                          gap: '12px',
                          borderTop: '1px solid var(--border-color)',
                          paddingTop: '16px',
                          flexWrap: 'wrap'
                        }}>
                          {agentDetails.latest_run?.status !== 'PAUSED' ? (
                            <Button
                              variant="secondary"
                              onClick={() => handleControlTask(agentDetails.current_task!.id, 'pause')}
                            >
                              ⏸ Pause Task
                            </Button>
                          ) : (
                            <Button
                              variant="success"
                              onClick={() => handleControlTask(agentDetails.current_task!.id, 'resume')}
                            >
                              ▶ Resume Task
                            </Button>
                          )}

                          <Button
                            variant="danger"
                            onClick={() => {
                              if (confirm('Are you sure you want to terminate this task run?')) {
                                handleControlTask(agentDetails.current_task!.id, 'terminate');
                              }
                            }}
                          >
                            🛑 Terminate Run
                          </Button>

                          {agentDetails.current_task.status !== 'BLOCKED' && (
                            <Button
                              variant="ghost"
                              onClick={() => handleControlTask(agentDetails.current_task!.id, 'block')}
                            >
                              🚫 Block Task
                            </Button>
                          )}
                        </div>
                      </div>
                    </Card>
                  ) : (
                    <Card title="Task Context">
                      <EmptyState
                        title="Idle Agent"
                        message="This agent is not currently executing any task run."
                      />
                    </Card>
                  )}

                  {/* Detail sub-tabs */}
                  <div style={{
                    display: 'flex',
                    borderBottom: '1px solid var(--border-color)',
                    gap: '16px'
                  }}>
                    {(['context', 'logs', 'handoffs'] as const).map((tab) => (
                      <button
                        key={tab}
                        onClick={() => setAgentDetailTab(tab)}
                        style={{
                          background: 'none',
                          border: 'none',
                          borderBottom: agentDetailTab === tab ? '2px solid var(--color-primary)' : 'none',
                          padding: '8px 16px',
                          color: agentDetailTab === tab ? 'var(--text-primary)' : 'var(--text-muted)',
                          fontWeight: agentDetailTab === tab ? 600 : 400,
                          cursor: 'pointer',
                          textTransform: 'capitalize',
                        }}
                      >
                        {tab === 'context' ? 'Task Artifacts & Approvals' : tab}
                      </button>
                    ))}
                  </div>

                  {/* Sub-tab content */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {agentDetailTab === 'context' && (
                      <>
                        <Card title="Generated Artifacts">
                          {agentDetails.artifacts.length === 0 ? (
                            <EmptyState title="No Artifacts" message="No artifacts generated yet." />
                          ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                              {agentDetails.artifacts.map((art) => (
                                <div
                                  key={art.id}
                                  style={{
                                    padding: '10px 14px',
                                    borderRadius: '6px',
                                    backgroundColor: 'rgba(255,255,255,0.02)',
                                    border: '1px solid var(--border-color)',
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center'
                                  }}
                                >
                                  <div>
                                    <span style={{ fontSize: '13px', fontWeight: 600 }}>{art.path}</span>
                                    <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block' }}>
                                      Type: {art.type} | Hash: {art.checksum}
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </Card>

                        <Card title="Active Safety Actions (Approvals)">
                          {agentDetails.actions.length === 0 ? (
                            <EmptyState title="No Safety Actions" message="No manual approval requests logged." />
                          ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                              {agentDetails.actions.map((act) => (
                                <div
                                  key={act.id}
                                  style={{
                                    padding: '10px 14px',
                                    borderRadius: '6px',
                                    backgroundColor: 'rgba(255,255,255,0.02)',
                                    border: '1px solid var(--border-color)',
                                    fontSize: '13px'
                                  }}
                                >
                                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                                    <span style={{ fontWeight: 600, color: 'var(--color-warning)' }}>
                                      {act.kind}
                                    </span>
                                    <StatusBadge status={act.status} />
                                  </div>
                                  <p style={{ margin: 0, fontFamily: 'monospace', fontSize: '12px' }}>
                                    {JSON.stringify(act.payload)}
                                  </p>
                                </div>
                              ))}
                            </div>
                          )}
                        </Card>
                      </>
                    )}

                    {agentDetailTab === 'logs' && (
                      <Card title="Agent Audit Log Trails">
                        {agentDetails.logs.length === 0 ? (
                          <EmptyState title="No logs found" message="No audit event trails registered." />
                        ) : (
                          <div style={{
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '8px',
                            maxHeight: '300px',
                            overflowY: 'auto'
                          }}>
                            {agentDetails.logs.map((log) => (
                              <div
                                key={log.id}
                                style={{
                                  padding: '8px 12px',
                                  fontSize: '12px',
                                  fontFamily: 'monospace',
                                  backgroundColor: 'rgba(255,255,255,0.01)',
                                  border: '1px solid var(--border-color)',
                                  borderRadius: '6px'
                                }}
                              >
                                <span style={{ color: 'var(--text-muted)' }}>
                                  [{new Date(log.created_at).toLocaleString()}]
                                </span>{' '}
                                <span style={{ color: 'var(--color-primary)' }}>
                                  {log.event_type}
                                </span>{' '}
                                - {JSON.stringify(log.payload_redacted)}
                              </div>
                            ))}
                          </div>
                        )}
                      </Card>
                    )}

                    {agentDetailTab === 'handoffs' && (
                      <Card title="Agent Handoff Transactions">
                        {agentDetails.handoffs.length === 0 ? (
                          <EmptyState title="No handoffs found" message="No collaborative handoffs logged." />
                        ) : (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {agentDetails.handoffs.map((ho) => (
                              <div
                                key={ho.id}
                                style={{
                                  padding: '10px 14px',
                                  borderRadius: '6px',
                                  backgroundColor: 'rgba(255,255,255,0.02)',
                                  border: '1px solid var(--border-color)',
                                  fontSize: '13px'
                                }}
                              >
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                                  <span>
                                    <strong>{ho.from_role}</strong> ➔ <strong>{ho.to_role}</strong>
                                  </span>
                                  <StatusBadge status={ho.status} />
                                </div>
                                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                                  Kind: {ho.kind} | Priority: {ho.priority} | Created: {new Date(ho.created_at).toLocaleString()}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </Card>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        );

      case 'runs':
        return (
          <Card title="Execution Runs & Cycles">
            <Table columns={runColumns} data={runs} emptyMessage="No runs executed yet." />
          </Card>
        );

      case 'prs': {
        const prTasks = tasks.filter((t) => t.status === 'PR_READY');

        const handleCopyPRDescription = () => {
          if (prDetails?.summary) {
            navigator.clipboard.writeText(prDetails.summary);
            alert('PR description copied to clipboard!');
          }
        };

        return (
          <div style={{
            display: 'flex',
            gap: '24px',
            height: 'calc(100vh - 120px)'
          }}>
            {/* Left panel: PR Queue */}
            <div style={{
              flex: '0 0 320px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px'
            }}>
              <Card title={`PR Queue (${prTasks.length})`}>
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                  overflowY: 'auto',
                  maxHeight: 'calc(100vh - 240px)'
                }}>
                  {prTasks.length === 0 ? (
                    <EmptyState
                      title="No PRs Ready"
                      message="There are currently no tasks waiting in the PR review queue."
                    />
                  ) : (
                    prTasks.map((t) => {
                      const isSelected = selectedPRTask?.id === t.id;
                      return (
                        <div
                          key={t.id}
                          onClick={() => setSelectedPRTask(t)}
                          style={{
                            padding: '16px',
                            borderRadius: '8px',
                            border: `1px solid ${
                              isSelected ? 'var(--color-primary)' : 'var(--border-color)'
                            }`,
                            backgroundColor: isSelected
                              ? 'rgba(74, 144, 226, 0.08)'
                              : 'var(--bg-card)',
                            cursor: 'pointer',
                            transition: 'all 0.2s',
                          }}
                        >
                          <div style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            marginBottom: '8px'
                          }}>
                            <span style={{
                              fontWeight: 700,
                              color: 'var(--color-primary)',
                              fontSize: '13px'
                            }}>
                              {t.key}
                            </span>
                            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                              {(t.risk_level || 'low').toUpperCase()} RISK
                            </span>
                          </div>
                          <h4 style={{
                            margin: 0,
                            fontSize: '14px',
                            fontWeight: 600,
                            color: 'var(--text-primary)'
                          }}>
                            {t.title}
                          </h4>
                        </div>
                      );
                    })
                  )}
                </div>
              </Card>
            </div>

            {/* Right panel: split details screen */}
            <div style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden'
            }}>
              {!selectedPRTask ? (
                <Card title="PR details">
                  <EmptyState
                    title="Select a PR to Review"
                    message="Choose a task from the queue to inspect diffs and tests."
                  />
                </Card>
              ) : isLoadingPRDetails ? (
                <Card title={`Reviewing ${selectedPRTask.key}`}>
                  <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}>
                    <span style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
                      Loading PR artifacts...
                    </span>
                  </div>
                </Card>
              ) : (
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '20px',
                  height: '100%',
                  overflowY: 'auto'
                }}>
                  {/* Title & Top Action bar */}
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    backgroundColor: 'var(--bg-card)',
                    padding: '16px 20px',
                    borderRadius: '8px',
                    border: '1px solid var(--border-color)',
                  }}>
                    <div>
                      <h2 style={{
                        margin: 0,
                        fontSize: '18px',
                        fontWeight: 700,
                        color: 'var(--text-primary)'
                      }}>
                        {selectedPRTask.key}: {selectedPRTask.title}
                      </h2>
                      <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                        Status: <strong style={{ color: 'var(--color-warning)' }}>PR_READY</strong>
                      </span>
                    </div>

                    <div style={{ display: 'flex', gap: '10px' }}>
                      <Button variant="ghost" onClick={handleOpenPROrTaskFolder}>
                        📂 Open Local Path
                      </Button>
                      <Button variant="danger" onClick={() => handlePRDecision('reject')}>
                        ❌ Reject
                      </Button>
                      <Button
                        variant="warning"
                        onClick={() => handlePRDecision('request_adjustment')}
                      >
                        ⚠️ Request Adjustments
                      </Button>
                      <Button variant="success" onClick={() => handlePRDecision('accept')}>
                        ✔ Accept & Merge
                      </Button>
                    </div>
                  </div>

                  {/* Details grid layout */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                    {/* Summary & Changed Files */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                      <Card
                        title="PR Description"
                        actions={
                          prDetails?.summary && (
                            <Button
                              variant="ghost"
                              onClick={handleCopyPRDescription}
                            >
                              Copy Description
                            </Button>
                          )
                        }
                      >
                        <div style={{
                          maxHeight: '300px',
                          overflowY: 'auto',
                          fontSize: '14px',
                          lineHeight: '1.6',
                          whiteSpace: 'pre-wrap',
                          color: 'var(--text-secondary)',
                          fontFamily: 'sans-serif',
                        }}>
                          {prDetails?.summary || 'No description found.'}
                        </div>
                      </Card>

                      <Card title="Changed Files">
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                          {(!prDetails?.changed_files || prDetails.changed_files.length === 0) ? (
                            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                              No modified files.
                            </span>
                          ) : (
                            prDetails.changed_files.map((file: string) => (
                              <div
                                key={file}
                                style={{
                                  fontSize: '13px',
                                  fontFamily: 'monospace',
                                  padding: '8px 12px',
                                  backgroundColor: 'rgba(255,255,255,0.02)',
                                  borderRadius: '6px',
                                  border: '1px solid var(--border-color)',
                                  color: 'var(--text-secondary)',
                                }}
                              >
                                {file}
                              </div>
                            ))
                          )}
                        </div>
                      </Card>

                      {prDetails?.risk_content && (
                        <Card title="Risk Report">
                          <pre style={{
                            margin: 0,
                            padding: '12px',
                            borderRadius: '6px',
                            border: '1px solid var(--border-color)',
                            backgroundColor: 'rgba(255,255,255,0.01)',
                            fontSize: '12px',
                            fontFamily: 'monospace',
                            whiteSpace: 'pre-wrap',
                            color: 'var(--text-secondary)',
                          }}>
                            {prDetails.risk_content}
                          </pre>
                        </Card>
                      )}
                    </div>

                    {/* Diffs & Test Runner Console */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                      <Card
                        title="Test Runner Console"
                        actions={
                          <Button
                            variant="primary"
                            disabled={isRerunningTests}
                            onClick={handleRerunPRTests}
                          >
                            {isRerunningTests ? 'Running...' : '🔄 Rerun Tests'}
                          </Button>
                        }
                      >
                        <div style={{
                          backgroundColor: '#1E1E1E',
                          borderRadius: '8px',
                          border: '1px solid var(--border-color)',
                          padding: '14px',
                          maxHeight: '300px',
                          overflowY: 'auto',
                        }}>
                          <pre style={{
                            margin: 0,
                            fontFamily: 'monospace',
                            fontSize: '12px',
                            color: '#4AF626',
                            whiteSpace: 'pre-wrap',
                          }}>
                            {testConsoleOutput || prDetails?.tests_content ||
                              'No test execution log loaded. Click Rerun Tests to execute.'}
                          </pre>
                        </div>
                      </Card>

                      {prDetails?.repair_content && (
                        <Card title="Repair Attempts Log">
                          <pre style={{
                            margin: 0,
                            padding: '12px',
                            borderRadius: '6px',
                            border: '1px solid var(--border-color)',
                            backgroundColor: 'rgba(255,255,255,0.01)',
                            fontSize: '12px',
                            fontFamily: 'monospace',
                            whiteSpace: 'pre-wrap',
                            color: 'var(--text-secondary)',
                          }}>
                            {prDetails.repair_content}
                          </pre>
                        </Card>
                      )}
                    </div>
                  </div>

                  {/* Unified Diffs patch viewer */}
                  {prDetails?.patch_content && (
                    <Card title="Unified Patch Diff Viewer">
                      <div style={{
                        maxHeight: '500px',
                        overflowY: 'auto',
                        border: '1px solid var(--border-color)',
                        borderRadius: '8px',
                        backgroundColor: '#1E1E1E',
                        padding: '16px',
                      }}>
                        <pre style={{
                          margin: 0,
                          fontFamily: 'monospace',
                          fontSize: '12px',
                          overflowX: 'auto'
                        }}>
                          {prDetails.patch_content.split('\n').map((line: string, idx: number) => {
                            let color = '#D4D4D4';
                            let bgColor = 'transparent';
                            if (line.startsWith('+') && !line.startsWith('+++')) {
                              color = '#4EC9B0';
                              bgColor = 'rgba(78, 201, 176, 0.15)';
                            } else if (line.startsWith('-') && !line.startsWith('---')) {
                              color = '#F44747';
                              bgColor = 'rgba(244, 71, 71, 0.15)';
                            } else if (line.startsWith('@@')) {
                              color = '#569CD6';
                            }
                            return (
                              <div
                                key={idx}
                                style={{
                                  color,
                                  backgroundColor: bgColor,
                                  padding: '2px 4px',
                                  borderRadius: '2px',
                                }}
                              >
                                {line}
                              </div>
                            );
                          })}
                        </pre>
                      </div>
                    </Card>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      }

      case 'worktrees':
        return (
          <Card title="Git Worktree Manager">
            {worktrees.length === 0 ? (
              <EmptyState
                title="No task worktrees"
                message="Task worktrees appear here after scheduler setup."
              />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {worktrees.map((item) => (
                  <div
                    key={`${item.task_id}-${item.path}`}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '110px 1fr 120px 90px 160px',
                      gap: '12px',
                      alignItems: 'center',
                      padding: '12px',
                      border: '1px solid var(--border-color)',
                      borderRadius: '8px',
                    }}
                  >
                    <strong>{item.task_key}</strong>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontFamily: 'monospace', fontSize: '12px' }}>
                        {item.branch || 'no branch'}
                      </div>
                      <div style={{
                        color: 'var(--text-muted)',
                        fontFamily: 'monospace',
                        fontSize: '11px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}>
                        {item.path}
                      </div>
                    </div>
                    <StatusBadge status={item.task_status} />
                    <span style={{ color: item.dirty ? 'var(--color-warning)' : 'var(--color-success)' }}>
                      {item.dirty ? 'dirty' : 'clean'}
                    </span>
                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                      <Button
                        variant="secondary"
                        disabled={!item.cleanup_eligible}
                        onClick={async () => {
                          await apiClient.cleanupWorktree(item.task_id);
                          loadProjectData();
                        }}
                      >
                        Cleanup
                      </Button>
                      <Button
                        variant="warning"
                        disabled={!item.last_commit}
                        onClick={async () => {
                          if (!item.last_commit) return;
                          await apiClient.revertWorktree(item.task_id, item.last_commit);
                          loadProjectData();
                        }}
                      >
                        Revert
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        );

      case 'models':
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: '300px' }}>
                <Card title="Active LLM Providers & Health">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div>
                      <span style={{
                        fontSize: '11px',
                        color: 'var(--text-muted)',
                        display: 'block'
                      }}>
                        ACTIVE PROVIDER
                      </span>
                      <strong style={{ fontSize: '16px', color: 'var(--color-primary)' }}>
                        LOCALFORGE (FAKE/LOCAL EMBEDDED)
                      </strong>
                    </div>
                    <div>
                      <span style={{
                        fontSize: '11px',
                        color: 'var(--text-muted)',
                        display: 'block'
                      }}>
                        HEALTH STATUS
                      </span>
                      <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        marginTop: '4px'
                      }}>
                        <span style={{
                          width: '10px',
                          height: '10px',
                          borderRadius: '50%',
                          backgroundColor: 'var(--color-success)',
                          boxShadow: '0 0 8px var(--color-success)',
                          display: 'inline-block'
                        }} />
                        <span style={{
                          fontSize: '14px',
                          fontWeight: 600,
                          color: 'var(--color-success)'
                        }}>
                          Healthy & Operational
                        </span>
                      </div>
                    </div>
                  </div>
                </Card>
              </div>

              <div style={{ flex: 2, minWidth: '350px' }}>
                <Card title="Available LLM Models">
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px' }}>
                    {models.length === 0 ? (
                      <EmptyState
                        title="No models detected"
                        message="Ensure the local LLM server is reachable."
                      />
                    ) : (
                      models.map((model) => (
                        <div
                          key={model}
                          style={{
                            padding: '12px 18px',
                            borderRadius: '8px',
                            border: '1px solid var(--border-color)',
                            background: 'rgba(255,255,255,0.01)',
                            fontSize: '13px',
                            fontFamily: 'monospace',
                            color: 'var(--text-primary)',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px'
                          }}
                        >
                          <span style={{
                            width: '6px',
                            height: '6px',
                            borderRadius: '50%',
                            backgroundColor: 'var(--color-primary)'
                          }} />
                          {model}
                        </div>
                      ))
                    )}
                  </div>
                </Card>
              </div>

              <div style={{ flex: 1, minWidth: '280px' }}>
                <Card title="Chief Engineer Usage">
                  {!chiefEngineerUsage ? (
                    <EmptyState
                      title="Usage unavailable"
                      message="Paid model usage could not be loaded."
                    />
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '10px' }}>
                        {[
                          ['Provider', chiefEngineerUsage.provider],
                          ['Model', chiefEngineerUsage.model],
                          ['API key', chiefEngineerUsage.api_key_configured ? 'configured' : 'missing'],
                          ['Calls', String(chiefEngineerUsage.calls.length)],
                          [
                            'Input tokens',
                            String(chiefEngineerUsage.calls.reduce((sum, call) => sum + call.input_tokens, 0)),
                          ],
                          [
                            'Output tokens',
                            String(chiefEngineerUsage.calls.reduce((sum, call) => sum + call.output_tokens, 0)),
                          ],
                          [
                            'Estimated cost',
                            `$${chiefEngineerUsage.calls
                              .reduce((sum, call) => sum + call.estimated_cost_usd, 0)
                              .toFixed(6)}`,
                          ],
                          ['Enabled', chiefEngineerUsage.enabled ? 'yes' : 'no'],
                        ].map(([label, value]) => (
                          <div
                            key={label}
                            style={{
                              padding: '10px',
                              border: '1px solid var(--border-color)',
                              borderRadius: '8px',
                              backgroundColor: 'rgba(255,255,255,0.01)',
                              minWidth: 0,
                            }}
                          >
                            <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                              {label}
                            </div>
                            <div style={{ fontSize: '12px', fontFamily: 'monospace', overflowWrap: 'anywhere' }}>
                              {value || 'n/a'}
                            </div>
                          </div>
                        ))}
                      </div>
                      <CodeBlock
                        code={JSON.stringify(chiefEngineerUsage.budget || {}, null, 2)}
                      />
                    </div>
                  )}
                </Card>
              </div>
            </div>

            <Card title="Visual Routing Editor">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {PIPELINE_ROLES.map((role) => {
                  const draft: Partial<ModelRoute> =
                    routeDrafts[role] || modelRoutes.find((r) => r.role === role) || {};
                  return (
                    <div
                      key={role}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '120px 1fr 1fr 1fr auto',
                        gap: '10px',
                        alignItems: 'center',
                        padding: '10px',
                        border: '1px solid var(--border-color)',
                        borderRadius: '8px',
                        backgroundColor: 'rgba(255,255,255,0.01)'
                      }}
                    >
                      <strong style={{ fontSize: '13px' }}>{role}</strong>
                      <input
                        value={draft.provider || 'localforge'}
                        onChange={(e) => handleRouteDraftChange(role, 'provider', e.target.value)}
                        style={{
                          padding: '8px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'var(--bg-input)',
                          color: 'var(--text-primary)'
                        }}
                      />
                      <input
                        value={draft.model_profile_id || ''}
                        placeholder={`${role.toLowerCase()}-local`}
                        onChange={(e) =>
                          handleRouteDraftChange(role, 'model_profile_id', e.target.value)
                        }
                        style={{
                          padding: '8px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'var(--bg-input)',
                          color: 'var(--text-primary)'
                        }}
                      />
                      <input
                        value={draft.endpoint_url || ''}
                        placeholder="endpoint optional"
                        onChange={(e) =>
                          handleRouteDraftChange(role, 'endpoint_url', e.target.value)
                        }
                        style={{
                          padding: '8px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'var(--bg-input)',
                          color: 'var(--text-primary)'
                        }}
                      />
                      <Button
                        variant="secondary"
                        onClick={() => handleSaveRoute(role)}
                        style={{ padding: '8px 12px' }}
                      >
                        Save
                      </Button>
                    </div>
                  );
                })}
              </div>
            </Card>

            <Card title="Agent Role Mappings (Routing Model configuration)">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {agents.length === 0 ? (
                  <EmptyState
                    title="No routing active"
                    message="No active agents mapped to models."
                  />
                ) : (
                  agents.map((a) => (
                    <div
                      key={a.id}
                      style={{
                        padding: '14px 18px',
                        borderRadius: '8px',
                        border: '1px solid var(--border-color)',
                        backgroundColor: 'rgba(255, 255, 255, 0.01)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: '12px'
                      }}
                    >
                      <div>
                        <strong style={{ fontSize: '15px' }}>{a.name}</strong>
                        <span style={{
                          fontSize: '11px',
                          color: 'var(--text-muted)',
                          marginLeft: '8px',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          border: '1px solid var(--border-color)',
                          textTransform: 'capitalize'
                        }}>
                          {a.role}
                        </span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                          Routed to model:
                        </span>
                        <code style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          backgroundColor: 'rgba(33, 150, 243, 0.08)',
                          border: '1px solid rgba(33, 150, 243, 0.2)',
                          color: 'var(--color-primary)',
                          fontSize: '13px'
                        }}>
                          {a.model_profile_id || 'gemini-2.5-pro'}
                        </code>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </Card>

            <Card title="Model Performance Metrics">
              {modelMetrics.length === 0 ? (
                <EmptyState
                  title="No model metrics"
                  message="Metrics appear after role routes or model usage are recorded."
                />
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
                  {modelMetrics.map((metric) => (
                    <div
                      key={`${metric.role}-${metric.model_profile_id}`}
                      style={{
                        padding: '12px',
                        border: '1px solid var(--border-color)',
                        borderRadius: '8px',
                      }}
                    >
                      <strong>{metric.role}</strong>
                      <div style={{ fontFamily: 'monospace', fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {metric.model_profile_id}
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
                        Success {(metric.success_rate * 100).toFixed(0)}% · Failure {(metric.failure_rate * 100).toFixed(0)}%
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        );

      case 'safety': {
        const activeRun = runs.find(
          (r) => r.status === 'RUNNING' || r.status === 'PAUSED'
        );

        const handleKillSwitch = async () => {
          if (!activeRun) {
            alert('No active runs to stop.');
            return;
          }
          if (
            confirm(
              'ARE YOU SURE YOU WANT TO TRIGGER THE EMERGENCY KILL SWITCH? ' +
                'This will halt all current run operations immediately.'
            )
          ) {
            try {
              await apiClient.commandRun(activeRun.id, 'stop');
              loadProjectData();
            } catch (err: any) {
              alert(err.message || 'Failed to trigger kill switch.');
            }
          }
        };

        const handleDecision = async (
          id: number,
          action: 'approve' | 'reject'
        ) => {
          try {
            await apiClient.decideApproval(id, action);
            loadProjectData();
          } catch (err: any) {
            alert(err.message || 'Failed to submit decision.');
          }
        };

        const handleLockProject = async () => {
          if (!activeProject) return;
          await apiClient.lockProject(activeProject.id);
          loadProjectData();
        };

        const handleExportAudit = async () => {
          if (!activeProject) return;
          setAuditExport(await apiClient.exportAuditEvents(activeProject.id));
        };

        const handleRevertUnsafeWorktree = async () => {
          const target = worktrees.find((item) => item.dirty && item.last_commit);
          if (!target || !target.last_commit) {
            alert('No dirty worktree with a checkpoint commit was found.');
            return;
          }
          await apiClient.revertWorktree(target.task_id, target.last_commit);
          loadProjectData();
        };

        // Extract policy fields
        const policyRules = policy?.rules || {};
        const policyName = policyRules.name || 'unattended_conservative';
        const allowedCmds: string[] = policyRules.allowed_commands || [];
        const blockedCmds: string[] = policyRules.blocked_commands || [];
        const protectedPaths: string[] = policyRules.protected_paths || [];
        const maxRepair = policyRules.max_repair_attempts ?? 3;
        const maxFiles = policyRules.max_files_touched ?? 10;

        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
              {/* Emergency controls */}
              <div style={{ flex: 1, minWidth: '320px' }}>
                <Card title="Safety Mode & Emergency Controls">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div>
                      <span style={{
                        fontSize: '11px',
                        color: 'var(--text-muted)',
                        display: 'block',
                      }}>
                        ACTIVE SAFETY POLICY
                      </span>
                      <span style={{
                        fontSize: '16px',
                        fontWeight: 700,
                        color: 'var(--color-success)',
                      }}>
                        {policyName.toUpperCase().replace('_', ' ')}
                      </span>
                    </div>

                    <div>
                      <span style={{
                        fontSize: '11px',
                        color: 'var(--text-muted)',
                        display: 'block',
                      }}>
                        POLICY DEFINITION FILE
                      </span>
                      <span style={{
                        fontSize: '13px',
                        fontFamily: 'monospace',
                        color: 'var(--text-secondary)',
                      }}>
                        {activeProject?.localforge_config_path ||
                          '.localforge/policies/default.yaml'}
                      </span>
                    </div>

                    <div>
                      <span style={{
                        fontSize: '11px',
                        color: 'var(--text-muted)',
                        display: 'block',
                        marginBottom: '4px',
                      }}>
                        SYSTEM CONTROL LOCK
                      </span>
                      {activeRun ? (
                        <div style={{
                          padding: '10px 12px',
                          borderRadius: '6px',
                          backgroundColor: 'rgba(239, 83, 80, 0.08)',
                          border: '1px solid var(--color-danger)',
                          color: 'var(--color-danger)',
                          fontSize: '13px',
                          fontWeight: 600,
                          textAlign: 'center',
                        }}>
                          ACTIVE RUN ENFORCED (RUNNING #{activeRun.id})
                        </div>
                      ) : (
                        <div style={{
                          padding: '10px 12px',
                          borderRadius: '6px',
                          backgroundColor: 'rgba(76, 175, 80, 0.08)',
                          border: '1px solid var(--color-success)',
                          color: 'var(--color-success)',
                          fontSize: '13px',
                          fontWeight: 600,
                          textAlign: 'center',
                        }}>
                          NO ACTIVE RUNS (STANDBY)
                        </div>
                      )}
                    </div>

                    <div style={{
                      borderTop: '1px solid var(--border-color)',
                      paddingTop: '16px',
                    }}>
                      <Button
                        variant="danger"
                        disabled={!activeRun}
                        onClick={handleKillSwitch}
                        style={{
                          width: '100%',
                          padding: '14px',
                          fontSize: '14px',
                          fontWeight: 700,
                          letterSpacing: '0.5px',
                        }}
                      >
                        🚨 TRIGGER EMERGENCY KILL SWITCH
                      </Button>
                      <p style={{
                        fontSize: '11px',
                        color: 'var(--text-muted)',
                        marginTop: '8px',
                        textAlign: 'center',
                        lineHeight: '1.4',
                      }}>
                        Halts the active run executor immediately by canceling the task scheduler.
                      </p>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '12px' }}>
                        <Button variant="warning" onClick={handleLockProject}>
                          Lock Project
                        </Button>
                        <Button variant="secondary" onClick={handleRevertUnsafeWorktree}>
                          Revert Unsafe Worktree
                        </Button>
                      </div>
                      <Button
                        variant="secondary"
                        onClick={handleExportAudit}
                        style={{ width: '100%', marginTop: '8px' }}
                      >
                        Export Audit Log
                      </Button>
                      {auditExport && (
                        <textarea
                          value={auditExport}
                          readOnly
                          rows={5}
                          style={{
                            width: '100%',
                            marginTop: '8px',
                            padding: '8px',
                            borderRadius: '6px',
                            border: '1px solid var(--border-color)',
                            backgroundColor: 'var(--bg-input)',
                            color: 'var(--text-secondary)',
                            fontFamily: 'monospace',
                            fontSize: '11px',
                          }}
                        />
                      )}
                    </div>
                  </div>
                </Card>
              </div>

              {/* Pending Approvals */}
              <div style={{ flex: 1.5, minWidth: '380px' }}>
                <Card title="Pending Safety Approvals Queue">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {pendingApprovals.length === 0 ? (
                      <EmptyState
                        title="All Checks Passed"
                        message="No actions are currently blocked or waiting for manual approval."
                      />
                    ) : (
                      pendingApprovals.map((app) => (
                        <div
                          key={app.id}
                          style={{
                            padding: '14px',
                            borderRadius: '8px',
                            border: '1px solid hsla(38, 92%, 50%, 0.3)',
                            backgroundColor: 'hsla(38, 92%, 50%, 0.08)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '10px',
                          }}
                        >
                          <div style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                          }}>
                            <span style={{
                              fontWeight: 700,
                              color: 'var(--color-warning)',
                              fontSize: '12px',
                              textTransform: 'uppercase',
                            }}>
                              {app.kind} REQUIRED
                            </span>
                            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                              Run #{app.run_id}
                            </span>
                          </div>
                          <p style={{
                            fontSize: '13px',
                            fontFamily: 'monospace',
                            margin: 0,
                            wordBreak: 'break-all',
                          }}>
                            {app.payload.cmd || app.payload.path || 'Access Request'}
                          </p>
                          <div style={{
                            display: 'flex',
                            gap: '8px',
                            alignSelf: 'flex-end',
                          }}>
                            <Button
                              variant="success"
                              onClick={() => handleDecision(app.id, 'approve')}
                            >
                              Approve
                            </Button>
                            <Button
                              variant="danger"
                              onClick={() => handleDecision(app.id, 'reject')}
                            >
                              Reject
                            </Button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </Card>
              </div>
            </div>

            {/* Allowed & Blocked Command Rules */}
            <Card
              title="Active Rules & Enforced Boundaries"
              actions={
                !isEditingPolicy ? (
                  <Button onClick={startEditingPolicy}>
                    ✏️ Edit Rules
                  </Button>
                ) : (
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <Button variant="ghost" onClick={() => setIsEditingPolicy(false)}>
                      Cancel
                    </Button>
                    <Button variant="success" onClick={handleSavePolicy}>
                      Save Policy
                    </Button>
                  </div>
                )
              }
            >
              {isEditingPolicy ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: '220px' }}>
                      <label style={{
                        display: 'block',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: 'var(--text-muted)',
                        marginBottom: '6px',
                      }}>
                        ALLOWED PATTERNS (one per line)
                      </label>
                      <textarea
                        value={policyAllowedCmds}
                        onChange={(e) => setPolicyAllowedCmds(e.target.value)}
                        rows={6}
                        style={{
                          width: '100%',
                          padding: '10px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'var(--bg-input)',
                          color: 'var(--text-primary)',
                          fontFamily: 'monospace',
                          fontSize: '12px',
                        }}
                        placeholder="e.g. npm test"
                      />
                    </div>
                    <div style={{ flex: 1, minWidth: '220px' }}>
                      <label style={{
                        display: 'block',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: 'var(--text-muted)',
                        marginBottom: '6px',
                      }}>
                        BLOCKED PATTERNS (one per line)
                      </label>
                      <textarea
                        value={policyBlockedCmds}
                        onChange={(e) => setPolicyBlockedCmds(e.target.value)}
                        rows={6}
                        style={{
                          width: '100%',
                          padding: '10px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'var(--bg-input)',
                          color: 'var(--text-primary)',
                          fontFamily: 'monospace',
                          fontSize: '12px',
                        }}
                        placeholder="e.g. rm -rf"
                      />
                    </div>
                    <div style={{ flex: 1, minWidth: '220px' }}>
                      <label style={{
                        display: 'block',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: 'var(--text-muted)',
                        marginBottom: '6px',
                      }}>
                        PROTECTED FILES & PATHS (one per line)
                      </label>
                      <textarea
                        value={policyProtectedPaths}
                        onChange={(e) => setPolicyProtectedPaths(e.target.value)}
                        rows={6}
                        style={{
                          width: '100%',
                          padding: '10px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'var(--bg-input)',
                          color: 'var(--text-primary)',
                          fontFamily: 'monospace',
                          fontSize: '12px',
                        }}
                        placeholder="e.g. .env"
                      />
                    </div>
                  </div>
                  <div style={{
                    display: 'flex',
                    gap: '16px',
                    borderTop: '1px solid var(--border-color)',
                    paddingTop: '16px',
                  }}>
                    <div style={{ flex: 1 }}>
                      <label style={{
                        display: 'block',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: 'var(--text-muted)',
                        marginBottom: '6px',
                      }}>
                        Max Repair Attempts
                      </label>
                      <input
                        type="number"
                        min={0}
                        value={policyMaxRepair}
                        onChange={(e) => setPolicyMaxRepair(Number(e.target.value))}
                        style={{
                          width: '100%',
                          padding: '10px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'var(--bg-input)',
                          color: 'var(--text-primary)',
                          fontSize: '13px',
                        }}
                      />
                    </div>
                    <div style={{ flex: 1 }}>
                      <label style={{
                        display: 'block',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: 'var(--text-muted)',
                        marginBottom: '6px',
                      }}>
                        Max Files Touched Limit
                      </label>
                      <input
                        type="number"
                        min={1}
                        value={policyMaxFiles}
                        onChange={(e) => setPolicyMaxFiles(Number(e.target.value))}
                        style={{
                          width: '100%',
                          padding: '10px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'var(--bg-input)',
                          color: 'var(--text-primary)',
                          fontSize: '13px',
                        }}
                      />
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
                    {/* Allowed Commands */}
                    <div style={{ flex: 1, minWidth: '250px' }}>
                      <h4 style={{
                        color: 'var(--color-success)',
                        fontWeight: 600,
                        marginBottom: '10px',
                        fontSize: '14px',
                      }}>
                        ✔ ALLOWED PATTERNS
                      </h4>
                      <div style={{
                        maxHeight: '200px',
                        overflowY: 'auto',
                        border: '1px solid var(--border-color)',
                        borderRadius: '8px',
                        padding: '12px',
                        backgroundColor: 'rgba(255,255,255,0.01)',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '6px',
                      }}>
                        {allowedCmds.length === 0 ? (
                          <span style={{
                            fontSize: '13px',
                            color: 'var(--text-muted)',
                          }}>None</span>
                        ) : (
                          allowedCmds.map((cmd) => (
                            <div key={cmd} style={{
                              fontSize: '12px',
                              fontFamily: 'monospace',
                              color: 'var(--text-secondary)',
                              padding: '4px 6px',
                              backgroundColor: 'rgba(255,255,255,0.02)',
                              borderRadius: '4px',
                            }}>
                              {cmd}
                            </div>
                          ))
                        )}
                      </div>
                    </div>

                    {/* Blocked Commands */}
                    <div style={{ flex: 1, minWidth: '250px' }}>
                      <h4 style={{
                        color: 'var(--color-danger)',
                        fontWeight: 600,
                        marginBottom: '10px',
                        fontSize: '14px',
                      }}>
                        ❌ BLOCKED COMMAND PATTERNS
                      </h4>
                      <div style={{
                        maxHeight: '200px',
                        overflowY: 'auto',
                        border: '1px solid var(--border-color)',
                        borderRadius: '8px',
                        padding: '12px',
                        backgroundColor: 'rgba(255,255,255,0.01)',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '6px',
                      }}>
                        {blockedCmds.length === 0 ? (
                          <span style={{
                            fontSize: '13px',
                            color: 'var(--text-muted)',
                          }}>None</span>
                        ) : (
                          blockedCmds.map((cmd) => (
                            <div key={cmd} style={{
                              fontSize: '12px',
                              fontFamily: 'monospace',
                              color: 'var(--color-danger)',
                              padding: '4px 6px',
                              backgroundColor: 'rgba(239, 83, 80, 0.05)',
                              borderRadius: '4px',
                            }}>
                              {cmd}
                            </div>
                          ))
                        )}
                      </div>
                    </div>

                    {/* Protected Paths */}
                    <div style={{ flex: 1, minWidth: '250px' }}>
                      <h4 style={{
                        color: 'var(--color-warning)',
                        fontWeight: 600,
                        marginBottom: '10px',
                        fontSize: '14px',
                      }}>
                        🔒 PROTECTED FILES & PATHS
                      </h4>
                      <div style={{
                        maxHeight: '200px',
                        overflowY: 'auto',
                        border: '1px solid var(--border-color)',
                        borderRadius: '8px',
                        padding: '12px',
                        backgroundColor: 'rgba(255,255,255,0.01)',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '6px',
                      }}>
                        {protectedPaths.length === 0 ? (
                          <span style={{
                            fontSize: '13px',
                            color: 'var(--text-muted)',
                          }}>None</span>
                        ) : (
                          protectedPaths.map((p) => (
                            <div key={p} style={{
                              fontSize: '12px',
                              fontFamily: 'monospace',
                              color: 'var(--color-warning)',
                              padding: '4px 6px',
                              backgroundColor: 'rgba(255, 179, 0, 0.05)',
                              borderRadius: '4px',
                            }}>
                              {p}
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>

                  <div style={{
                    display: 'flex',
                    gap: '24px',
                    borderTop: '1px solid var(--border-color)',
                    paddingTop: '16px',
                    fontSize: '13px',
                  }}>
                    <div>
                      <span style={{ color: 'var(--text-muted)', marginRight: '6px' }}>
                        Max Repair Attempts:
                      </span>
                      <strong style={{ color: 'var(--color-primary)' }}>{maxRepair}</strong>
                    </div>
                    <div>
                      <span style={{ color: 'var(--text-muted)', marginRight: '6px' }}>
                        Max Files Touched Limit:
                      </span>
                      <strong style={{ color: 'var(--color-primary)' }}>{maxFiles}</strong>
                    </div>
                  </div>
                </div>
              )}
            </Card>

            {/* Policy Revision History */}
            {policyRules.history && policyRules.history.length > 0 && (
              <Card title="Policy Revision History">
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px'
                }}>
                  {policyRules.history.map((h: any) => (
                    <div
                      key={h.version}
                      style={{
                        padding: '14px',
                        borderRadius: '8px',
                        border: '1px solid var(--border-color)',
                        backgroundColor: 'rgba(255, 255, 255, 0.01)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '14px' }}>
                          Version {h.version}
                        </div>
                        <div style={{
                          fontSize: '12px',
                          color: 'var(--text-muted)'
                        }}>
                          Saved on {new Date(h.updated_at).toLocaleString()}
                        </div>
                        <div style={{
                          fontSize: '12px',
                          color: 'var(--text-secondary)',
                          marginTop: '4px'
                        }}>
                          Allowed: {h.rules?.allowed_commands?.length || 0} |{' '}
                          Blocked: {h.rules?.blocked_commands?.length || 0} |{' '}
                          Protected: {h.rules?.protected_paths?.length || 0}
                        </div>
                      </div>
                      <Button
                        variant="secondary"
                        onClick={() => handleRestorePolicyVersion(h.version)}
                      >
                        Revert to Version {h.version}
                      </Button>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        );
      }

      case 'skills':
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
              {/* Left Column: Skills Directory */}
              <div style={{ flex: 2, minWidth: '350px' }}>
                <Card title="Workspace Skills Registry">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {skills.map((skill) => (
                      <div
                        key={skill.name}
                        style={{
                          padding: '14px',
                          borderRadius: '8px',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'rgba(255,255,255,0.01)',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          gap: '16px'
                        }}
                      >
                        <div style={{
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '4px',
                          flex: 1
                        }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <strong style={{ fontSize: '15px', color: 'var(--text-primary)' }}>
                              {skill.name}
                            </strong>
                            <span style={{
                              fontSize: '10px',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              backgroundColor:
                                skill.source === 'builtin'
                                  ? 'rgba(76, 175, 80, 0.08)'
                                  : 'rgba(33, 150, 243, 0.08)',
                              border:
                                skill.source === 'builtin'
                                  ? '1px solid rgba(76, 175, 80, 0.2)'
                                  : '1px solid rgba(33, 150, 243, 0.2)',
                              color:
                                skill.source === 'builtin'
                                  ? 'var(--color-success)'
                                  : 'var(--color-primary)'
                            }}>
                              {skill.source}
                            </span>
                          </div>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                            <strong>Purpose:</strong> {skill.purpose}
                          </span>
                          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                            <strong>Triggers:</strong> {skill.triggers.join(', ') || 'none'}
                          </span>
                          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                            <strong>Status:</strong> {(skill.enabled ?? true) ? 'enabled' : 'disabled'} ·{' '}
                            <strong>Success:</strong>{' '}
                            {skill.success_rate == null ? 'n/a' : `${Math.round(skill.success_rate * 100)}%`} ·{' '}
                            <strong>Last used:</strong> {skill.last_used_at || 'never'}
                          </span>
                        </div>
                        <div>
                          <Button
                            variant={(skill.enabled ?? true) ? 'warning' : 'success'}
                            onClick={() => handleToggleSkill(skill)}
                            style={{ padding: '6px 10px', fontSize: '12px' }}
                          >
                            {(skill.enabled ?? true) ? 'Disable' : 'Enable'}
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              </div>

              {/* Right Column: Register a New Skill Form */}
              <div style={{ flex: 1, minWidth: '280px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <Card title="Register New Workspace Skill">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div>
                      <label style={{
                        display: 'block',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: 'var(--text-muted)',
                        marginBottom: '6px'
                      }}>
                        SKILL ID / NAME
                      </label>
                      <input
                        type="text"
                        value={newSkillName}
                        onChange={(e) => setNewSkillName(e.target.value)}
                        placeholder="e.g. database-migrator"
                        style={{
                          width: '100%',
                          padding: '10px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'var(--bg-input)',
                          color: 'var(--text-primary)',
                          fontSize: '13px'
                        }}
                      />
                    </div>

                    <div>
                      <label style={{
                        display: 'block',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: 'var(--text-muted)',
                        marginBottom: '6px'
                      }}>
                        TRIGGER CONDITION DESCRIPTION
                      </label>
                      <textarea
                        value={newSkillTrigger}
                        onChange={(e) => setNewSkillTrigger(e.target.value)}
                        placeholder="e.g. When performing SQLite schema migrations"
                        rows={3}
                        style={{
                          width: '100%',
                          padding: '10px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'var(--bg-input)',
                          color: 'var(--text-primary)',
                          fontSize: '13px'
                        }}
                      />
                    </div>

                    <Button
                      variant="primary"
                      onClick={handleAddSkill}
                      style={{
                        width: '100%',
                        paddingTop: '10px',
                        paddingBottom: '10px'
                      }}
                    >
                      Register Skill
                    </Button>
                  </div>
                </Card>
              </div>
            </div>
          </div>
        );

      case 'memory':
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
              {/* Left Column: Project Memory Facts */}
              <div style={{ flex: 2, minWidth: '350px' }}>
                <Card title="Project Short-Term & Long-Term Memory facts">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {projectMemory.length === 0 ? (
                      <EmptyState
                        title="Memory is blank"
                        message="Add project facts or wait for agents to register context."
                      />
                    ) : (
                      projectMemory.map((item) => (
                        <div
                          key={item.id}
                          style={{
                            padding: '14px',
                            borderRadius: '8px',
                            border: item.pinned
                              ? '1px solid hsla(38, 92%, 50%, 0.3)'
                              : '1px solid var(--border-color)',
                            backgroundColor: item.pinned
                              ? 'hsla(38, 92%, 50%, 0.04)'
                              : item.status === 'stale'
                              ? 'rgba(255,255,255,0.01)'
                              : 'rgba(255,255,255,0.02)',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            gap: '16px'
                          }}
                        >
                          <div style={{
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '4px',
                            flex: 1
                          }}>
                            <p style={{
                              margin: 0,
                              fontSize: '13px',
                              color: item.status === 'stale'
                                ? 'var(--text-muted)'
                                : 'var(--text-primary)',
                              textDecoration: item.status === 'stale' ? 'line-through' : 'none'
                            }}>
                              {item.fact}
                            </p>
                            <div style={{ display: 'flex', gap: '8px', fontSize: '10px' }}>
                              <span style={{
                                color: 'var(--text-muted)',
                                fontWeight: 600,
                                textTransform: 'uppercase'
                              }}>
                                {item.kind.replace('_', ' ')}
                              </span>
                              {item.pinned && (
                                <span style={{ color: 'var(--color-warning)', fontWeight: 600 }}>
                                  PINNED
                                </span>
                              )}
                              <span style={{
                                color: item.status === 'active'
                                  ? 'var(--color-success)'
                                  : 'var(--text-muted)',
                                fontWeight: 600,
                                textTransform: 'uppercase'
                              }}>
                                {item.status}
                              </span>
                            </div>
                          </div>

                          <div style={{ display: 'flex', gap: '8px' }}>
                            <Button
                              variant="ghost"
                              onClick={() => handlePinMemory(item)}
                              style={{ padding: '4px 8px', fontSize: '12px' }}
                            >
                              {item.pinned ? 'Unpin' : 'Pin'}
                            </Button>
                            <Button
                              variant="secondary"
                              onClick={() => handleStaleMemory(item)}
                              style={{ padding: '4px 8px', fontSize: '12px' }}
                            >
                              {item.status === 'stale' ? 'Activate' : 'Mark Stale'}
                            </Button>
                            <Button
                              variant="danger"
                              onClick={() => handleDeleteMemory(item.id)}
                              style={{ padding: '4px 8px', fontSize: '12px' }}
                            >
                              Delete
                            </Button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </Card>
              </div>

              {/* Right Column: Register a New Fact Form */}
              <div style={{ flex: 1, minWidth: '280px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <Card title="Add Project Fact">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div>
                      <label style={{
                        display: 'block',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: 'var(--text-muted)',
                        marginBottom: '6px'
                      }}>
                        MEMORY TYPE
                      </label>
                      <select
                        value={newMemoryKind}
                        onChange={(e) => setNewMemoryKind(e.target.value)}
                        style={{
                          width: '100%',
                          padding: '10px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'var(--bg-input)',
                          color: 'var(--text-primary)',
                          fontSize: '13px'
                        }}
                      >
                        <option value="stack_fact">Stack fact</option>
                        <option value="test_command">Test command</option>
                        <option value="user_preference">User preference</option>
                        <option value="known_pitfall">Known pitfall</option>
                        <option value="resolved_blocker">Resolved blocker</option>
                        <option value="model_performance_note">Model performance note</option>
                      </select>
                    </div>
                    <div>
                      <label style={{
                        display: 'block',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: 'var(--text-muted)',
                        marginBottom: '6px'
                      }}>
                        NEW PROJECT FACT DESCRIPTION
                      </label>
                      <textarea
                        value={newMemoryFact}
                        onChange={(e) => setNewMemoryFact(e.target.value)}
                        placeholder="e.g. API uses Bearer Token authentication schema in staging"
                        rows={4}
                        style={{
                          width: '100%',
                          padding: '10px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'var(--bg-input)',
                          color: 'var(--text-primary)',
                          fontSize: '13px'
                        }}
                      />
                    </div>

                    <Button
                      variant="primary"
                      onClick={handleAddMemoryFact}
                      style={{
                        width: '100%',
                        paddingTop: '10px',
                        paddingBottom: '10px'
                      }}
                    >
                      Add Fact
                    </Button>
                  </div>
                </Card>

                <Card title="Memory Backup">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <select
                      value={memoryFormat}
                      onChange={(e) => setMemoryFormat(e.target.value as 'json' | 'yaml')}
                      style={{
                        padding: '8px',
                        borderRadius: '6px',
                        border: '1px solid var(--border-color)',
                        backgroundColor: 'var(--bg-input)',
                        color: 'var(--text-primary)'
                      }}
                    >
                      <option value="json">JSON</option>
                      <option value="yaml">YAML</option>
                    </select>
                    <Button variant="secondary" onClick={handleExportMemory}>
                      Export
                    </Button>
                    <textarea
                      value={memoryExport}
                      readOnly
                      rows={5}
                      style={{
                        width: '100%',
                        padding: '10px',
                        borderRadius: '6px',
                        border: '1px solid var(--border-color)',
                        backgroundColor: 'var(--bg-input)',
                        color: 'var(--text-secondary)',
                        fontFamily: 'monospace',
                        fontSize: '12px'
                      }}
                    />
                    <textarea
                      value={memoryImport}
                      onChange={(e) => setMemoryImport(e.target.value)}
                      placeholder="Paste backup payload"
                      rows={5}
                      style={{
                        width: '100%',
                        padding: '10px',
                        borderRadius: '6px',
                        border: '1px solid var(--border-color)',
                        backgroundColor: 'var(--bg-input)',
                        color: 'var(--text-primary)',
                        fontFamily: 'monospace',
                        fontSize: '12px'
                      }}
                    />
                    <Button variant="primary" onClick={handleImportMemory}>
                      Import
                    </Button>
                  </div>
                </Card>
              </div>
            </div>
          </div>
        );

      case 'v3-dashboard':
        return activeProject ? (
          <V3Dashboard projectId={activeProject.id} />
        ) : (
          <EmptyState title="No Project Selected" message="Please select a project first." />
        );

      case 'kanban':
        return activeProject ? (
          <KanbanBoard tasks={tasks} onTaskClick={setSelectedTask} />
        ) : (
          <EmptyState title="No Project Selected" message="Please select a project first." />
        );

      case 'settings':
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <Card title="Project Settings">
              {!projectSettings ? (
                <EmptyState title="Settings unavailable" message="Project settings could not be loaded." />
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px' }}>
                  {[
                    ['Project path', projectSettings.project_path],
                    ['Default branch', projectSettings.default_branch],
                    ['Git provider', projectSettings.git_provider],
                    ['PR provider', projectSettings.pr_provider],
                    ['Model endpoint', projectSettings.model_endpoint],
                    ['Sandbox mode', projectSettings.sandbox_mode],
                  ].map(([label, value]) => (
                    <div key={label} style={{ padding: '12px', border: '1px solid var(--border-color)', borderRadius: '8px' }}>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                        {label}
                      </div>
                      <div style={{ fontFamily: 'monospace', fontSize: '12px', overflowWrap: 'anywhere' }}>
                        {value || 'not configured'}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
            <Card title="Resource Limits">
              <CodeBlock
                code={JSON.stringify(projectSettings?.resource_limits || {}, null, 2)}
              />
            </Card>
            <Card title="UI Preferences">
              <CodeBlock
                code={JSON.stringify(projectSettings?.ui_preferences || {}, null, 2)}
              />
            </Card>
          </div>
        );

      default:
        return (
          <Card title="View">
            <EmptyState title="Tab View under construction" message="Phase updates will deploy view states here." />
          </Card>
        );
    }
  };

  const timelineItems: TimelineItem[] = useMemo(() => events.map((ev) => {
    let type: TimelineItem['type'] = 'info';
    if (ev.event_type.includes('succeeded') || ev.event_type.includes('allowed')) {
      type = 'success';
    } else if (ev.event_type.includes('failed') || ev.event_type.includes('blocked')) {
      type = 'danger';
    } else if (ev.event_type.includes('started')) {
      type = 'primary';
    }
    return {
      title: ev.event_type,
      subtitle: ev.payload.action || ev.payload.status || '',
      content: <pre style={{ fontSize: '11px' }}>{JSON.stringify(ev.payload, null, 2)}</pre>,
      type,
    };
  }), [events]);

  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: 'var(--bg-app)' }}>
      {/* Sidebar Navigation */}
      <div style={{
        width: 'var(--sidebar-width)',
        backgroundColor: 'var(--bg-sidebar)',
        borderRight: '1px solid var(--border-color)',
        padding: '24px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '24px',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <h2 style={{ fontSize: '18px', fontWeight: 700, letterSpacing: '0.5px' }}>
            LocalForge OS
          </h2>
        </div>

        {/* Project Selector */}
        <div>
          <label style={{
            display: 'block',
            fontSize: '11px',
            textTransform: 'uppercase',
            fontWeight: 600,
            color: 'var(--text-muted)',
            marginBottom: '8px',
          }}>
            Active Project
          </label>
          {projects.length > 0 ? (
            <select
              value={activeProject?.id || ''}
              onChange={(e) => {
                const proj = projects.find((p) => p.id === parseInt(e.target.value, 10));
                if (proj) setActiveProject(proj);
              }}
              style={{
                width: '100%',
                padding: '10px',
                borderRadius: '8px',
                backgroundColor: 'var(--bg-input)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-primary)',
                outline: 'none',
                cursor: 'pointer',
              }}
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          ) : (
            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No projects</span>
          )}
        </div>

        {/* Sidebar Tabs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
          {(
            [
              'mission-control',
              'prd-backlog',
              'agents',
              'runs',
              'prs',
              'worktrees',
              'models',
              'skills',
              'memory',
              'safety',
              'v3-dashboard',
              'kanban',
              'settings',
            ] as Tab[]
          ).map((tab) => {
            const active = currentTab === tab;
            return (
              <a
                key={tab}
                href={`#/${tab}`}
                style={{
                  display: 'block',
                  padding: '10px 16px',
                  borderRadius: '8px',
                  fontSize: '14px',
                  fontWeight: 500,
                  color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                  backgroundColor: active ? 'var(--color-primary)' : 'transparent',
                  textDecoration: 'none',
                  transition: 'all 0.2s',
                }}
              >
                {tab.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
              </a>
            );
          })}
        </div>

        {/* Connectivity Status Indicator */}
        <div style={{
          padding: '12px',
          borderRadius: '8px',
          backgroundColor: 'rgba(255, 255, 255, 0.02)',
          border: '1px solid var(--border-color)',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px' }}>
            <span style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: backendHealthy ? 'var(--color-success)' : 'var(--color-danger)',
              boxShadow: `0 0 8px ${backendHealthy ? 'var(--color-success)' : 'var(--color-danger)'}`,
            }} />
            <span>API Server: {backendHealthy ? 'Online' : 'Offline'}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px' }}>
            <span style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: sseConnected ? 'var(--color-success)' : 'var(--color-danger)',
              boxShadow: `0 0 8px ${sseConnected ? 'var(--color-success)' : 'var(--color-danger)'}`,
            }} />
            <span>Live Stream: {sseConnected ? 'Subscribed' : 'Reconnecting'}</span>
          </div>
        </div>
      </div>

      {/* Main Workspace & Sidebar Event Log */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div style={{
          flex: 1,
          padding: '40px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '24px',
        }}>
          {error && <Alert type="error">{error}</Alert>}
          {renderTabContent()}
        </div>

        {/* Real-time events right sidebar panel */}
        <div style={{
          width: '320px',
          backgroundColor: 'var(--bg-sidebar)',
          borderLeft: '1px solid var(--border-color)',
          padding: '24px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600 }}>Real-time Operations Stream</h3>
          <Timeline items={timelineItems} />
        </div>
      </div>
    </div>
  );
}
