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

const wouldCreateCycle = (
  taskId: number,
  newDeps: number[],
  allTasks: Task[]
): boolean => {
  const visited = new Set<number>();
  const queue = [...newDeps];
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (current === taskId) return true;
    if (!visited.has(current)) {
      visited.add(current);
      const task = allTasks.find((t) => t.id === current);
      if (task && task.dependency_task_ids) {
        queue.push(...task.dependency_task_ids);
      }
    }
  }
  return false;
};


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

  useEffect(() => {
    if (editingTask) {
      setEditTitle(editingTask.title);
      setEditDesc(editingTask.description);
      setEditRisk(editingTask.risk_level || 'low');
      setEditCriteria(editingTask.acceptance_criteria?.join('\n') || '');
      setEditDeps(editingTask.dependency_task_ids?.join(', ') || '');
    }
  }, [editingTask]);

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
    ])
      .then(([tData, rData, aData, mData, pData, paData, eData]) => {
        setTasks(tData);
        setRuns(rData);
        setAgents(aData);
        setModels(mData.models);
        setPolicy(pData);
        setPendingApprovals(paData);
        setEpics(eData);
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
    ];
    if (reloadEvents.includes(event.event_type)) {
      loadProjectData();
    }
  }, [loadProjectData]);

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

  const agentColumns: Column<Agent>[] = [
    {
      header: 'Name',
      accessor: (a) => <span style={{ fontWeight: 600 }}>{a.name}</span>,
    },
    {
      header: 'Role',
      accessor: (a) => <span style={{ textTransform: 'capitalize' }}>{a.role}</span>,
    },
    {
      header: 'Status',
      accessor: (a) => <StatusBadge status={a.status} />,
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
          <Card title="Active Coding Agents">
            <Table columns={agentColumns} data={agents} emptyMessage="No autonomous agents active." />
          </Card>
        );

      case 'runs':
        return (
          <Card title="Execution Runs & Cycles">
            <Table columns={runColumns} data={runs} emptyMessage="No runs executed yet." />
          </Card>
        );

      case 'prs':
        return (
          <Card title="Pull Requests Ready">
            <EmptyState
              title="Local PR Factory"
              message="Tasks marked PR_READY with valid git worktree changes and test metadata."
            />
          </Card>
        );

      case 'worktrees':
        return (
          <Card title="Git Worktree Manager">
            <EmptyState
              title="Filesystem Sandboxes"
              message="View active git task branches and clean up orphan directories."
            />
          </Card>
        );

      case 'models':
        return (
          <Card title="Configured LLM Models">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px' }}>
              {models.map((model) => (
                <div
                  key={model}
                  style={{
                    padding: '16px 24px',
                    borderRadius: '8px',
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-card)',
                    fontSize: '14px',
                    fontWeight: 600,
                  }}
                >
                  {model}
                </div>
              ))}
            </div>
          </Card>
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
            <Card title="Active Rules & Enforced Boundaries">
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
            </Card>
          </div>
        );
      }

      default:
        return (
          <Card title={currentTab.toUpperCase().replace('-', ' ')}>
            <EmptyState title="Tab View under construction" message="Phase updates will deploy view states here." />
          </Card>
        );
    }
  };

  const timelineItems: TimelineItem[] = events.map((ev) => {
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
  });

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
