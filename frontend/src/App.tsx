import { useState, useEffect, useCallback } from 'react';
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
import { EmptyState } from './components/EmptyState';
import { CodeBlock } from './components/CodeBlock';
import { V3Dashboard } from './components/V3Dashboard';
import { KanbanBoard } from './components/KanbanBoard';
import { AppSidebar, type AppTab } from './components/AppSidebar';
import { OperationsStream } from './components/OperationsStream';
import { POChatView } from './components/POChatView';
import { ComplianceTestsView } from './components/ComplianceTestsView';
import { SkillsEditorView } from './components/SkillsEditorView';
import { ModelSettingsView } from './components/ModelSettingsView';
import { TracingTimelineView, type TraceSpanItem } from './components/TracingTimelineView';
import { HITLApprovalModal, type HITLGateData } from './components/HITLApprovalModal';
import { wouldCreateCycle } from './utils/taskGraph';


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


export default function App() {
  // Navigation & Project selection
  const [currentTab, setCurrentTab] = useState<AppTab>('mission-control');
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);

  // Persistent Chat Messages across tab navigation
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(() => {
    const saved = localStorage.getItem('localforge_po_chat_messages');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch (e) {
        console.error(e);
      }
    }
    return [
      {
        id: '1',
        sender: 'Scrum Master',
        text: 'Olá Product Owner! Sou o **Scrum Master** do LocalForge OS. Envie o seu `PRD.md` e arquivos visuais/schemas de interface (`.png`, `.jpg`, `.svg`) abaixo para iniciarmos a Etapa 2 de criação do Backlog da Squad.',
        timestamp: new Date().toLocaleTimeString(),
      },
    ];
  });

  useEffect(() => {
    localStorage.setItem('localforge_po_chat_messages', JSON.stringify(chatMessages));
  }, [chatMessages]);

  const handleSendChatMessage = async (text: string, files: File[]) => {
    const fileNames = files.map((f) => f.name);
    const poMsg: ChatMessage = {
      id: Date.now().toString(),
      sender: 'PO',
      text,
      timestamp: new Date().toLocaleTimeString(),
      attachments: fileNames.length > 0 ? fileNames : undefined,
    };
    setChatMessages((prev) => [...prev, poMsg]);

    try {
      const chatRes = await apiClient.poChat(text, fileNames, activeProject?.id);
      if (chatRes.project) {
        setActiveProject(chatRes.project);
        const [projs, tData] = await Promise.all([
          apiClient.fetchProjects(),
          apiClient.fetchTasks(chatRes.project.id),
        ]);
        setProjects(projs);
        setTasks(tData);
      }
      const smResponse: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: 'Scrum Master',
        text: chatRes.reply,
        timestamp: new Date().toLocaleTimeString(),
      };
      setChatMessages((prev) => [...prev, smResponse]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: 'Scrum Master',
        text: `Erro ao comunicar com a Squad: ${err.message || err}`,
        timestamp: new Date().toLocaleTimeString(),
      };
      setChatMessages((prev) => [...prev, errorMsg]);
    }
  };

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
  const [telemetrySpans, setTelemetrySpans] = useState<any[]>([]);
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
      const validTabs: AppTab[] = [
        'chat',
        'kanban',
        'tests',
        'skills',
        'settings',
      ];
      if (validTabs.includes(hash as AppTab)) {
        setCurrentTab(hash as AppTab);
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
          setActiveProject(data[data.length - 1]);
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
      apiClient.fetchTasks(activeProject.id).catch(() => []),
      apiClient.fetchRuns(activeProject.id).catch(() => []),
      apiClient.fetchAgents().catch(() => []),
      apiClient.fetchModels().catch(() => ({ provider: '', base_url: '', default_model: '', models: [] })),
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
        const safeTasks = Array.isArray(tData) ? tData : [];
        const safeRuns = Array.isArray(rData) ? rData : [];
        const safeAgents = Array.isArray(aData) ? aData : [];
        const safeModels = Array.isArray(mData?.models) ? mData.models : [];
        const safePendingApprovals = Array.isArray(paData) ? paData : [];
        const safeEpics = Array.isArray(eData) ? eData : [];
        const safeModelRoutes = Array.isArray(mrData) ? mrData : [];
        const safeMemData = Array.isArray(memData) ? memData : [];
        const safeSkillsData = Array.isArray(skillsData) ? skillsData : [];
        const safeWorktreeData = Array.isArray(worktreeData) ? worktreeData : [];
        const safeModelMetricData = Array.isArray(modelMetricData) ? modelMetricData : [];

        setTasks(safeTasks);
        setRuns(safeRuns);
        setAgents(safeAgents);
        setModels(safeModels);
        setPolicy(pData);
        setPendingApprovals(safePendingApprovals);
        setEpics(safeEpics);
        setModelRoutes(safeModelRoutes);
        setRouteDrafts(
          Object.fromEntries(safeModelRoutes.map((route) => [route.role, route]))
        );
        setProjectMemory(safeMemData);
        setSkills(safeSkillsData);
        setWorktrees(safeWorktreeData);
        setModelMetrics(safeModelMetricData);
        setChiefEngineerUsage(chiefEngineerData);
        setProjectSettings(settingsData);
        setError(null);
      })
      .catch((err) => {
        console.error('loadProjectData error:', err);
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

    if (event.event_type === 'task.agent_action' && event.payload) {
      const { task_id, key, agent_role, action_summary } = event.payload;
      setTasks((prev) =>
        prev.map((t) =>
          t.id === task_id || t.key === key
            ? ({ ...t, agent_action: { agent_role, action_summary } } as any)
            : t
        )
      );
    }

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
  }, [loadProjectData]);

  // Poll Telemetry Spans for Timeline
  useEffect(() => {
    if (!activeProject) return;
    const fetchSpans = () => {
      apiClient.fetchTelemetrySpans(activeProject.id).then(setTelemetrySpans).catch(() => {});
    };
    fetchSpans();
    const interval = setInterval(fetchSpans, 2000);
    return () => clearInterval(interval);
  }, [activeProject]);

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
      case 'chat':
        return (
          <POChatView
            activeProject={activeProject}
            messages={chatMessages}
            onSendMessage={handleSendChatMessage}
            onNavigateToTab={(tab) => setCurrentTab(tab as AppTab)}
          />
        );
      case 'kanban':
        return (
          <KanbanBoard
            tasks={tasks}
            activeProjectId={activeProject?.id}
            onTaskClick={(task) => setSelectedTask(task)}
            onRefresh={loadProjectData}
            onResetAll={() => {
              setActiveProject(null);
              setProjects([]);
              setTasks([]);
              setChatMessages([
                {
                  id: '1',
                  sender: 'Scrum Master',
                  text: 'Olá Product Owner! Sou o **Scrum Master** do LocalForge OS. Envie o seu `PRD.md` e arquivos visuais/schemas de interface (`.png`, `.jpg`, `.svg`) abaixo para iniciarmos a Etapa 2 de criação do Backlog da Squad.',
                  timestamp: new Date().toLocaleTimeString(),
                },
              ]);
              localStorage.removeItem('localforge_po_chat_messages');
            }}
          />
        );
      case 'tests':
        return (
          <div className="space-y-6">
            <TracingTimelineView spans={telemetrySpans} />
            <ComplianceTestsView onNavigateToTab={(tab) => setCurrentTab(tab as AppTab)} />
          </div>
        );
      case 'skills':
        return <SkillsEditorView />;
      case 'settings':
        return <ModelSettingsView />;
      default:
        return (
          <POChatView
            activeProject={activeProject}
            onNavigateToTab={(tab) => setCurrentTab(tab as AppTab)}
            onSelectProject={async (projId) => {
              try {
                const freshProjects = await apiClient.fetchProjects();
                setProjects(freshProjects);
                const targetProj = freshProjects.find((p) => p.id === projId);
                if (targetProj) {
                  setActiveProject(targetProj);
                }
              } catch (err) {
                console.error('Error selecting project:', err);
              }
            }}
          />
        );
    }
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: 'var(--bg-app)' }}>
      <AppSidebar
        projects={projects}
        activeProject={activeProject}
        currentTab={currentTab}
        backendHealthy={backendHealthy}
        sseConnected={sseConnected}
        onProjectChange={setActiveProject}
        onTabChange={(tab) => setCurrentTab(tab)}
      />
      {/* Main workspace and live event stream */}
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
        <OperationsStream events={events} />
      </div>
    </div>
  );
}
