import { useState, useEffect, useCallback } from 'react';
import {
  apiClient,
  type Project,
  type Task,
  type Run,
  type Agent,
  type Artifact,
  type Policy,
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

  // Live SSE events
  const [events, setEvents] = useState<LifecycleEventPayload[]>([]);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
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
    ])
      .then(([tData, rData, aData, mData, pData]) => {
        setTasks(tData);
        setRuns(rData);
        setAgents(aData);
        setModels(mData.models);
        setPolicy(pData);
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
    // Reload state if task status changed or runs modified
    if (['task.status_changed', 'run.started'].includes(event.event_type)) {
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
      case 'mission-control':
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ display: 'flex', gap: '24px', alignItems: 'stretch' }}>
              <div style={{ flex: 2, display: 'flex', flexDirection: 'column', gap: '24px' }}>
                <Card title="Project Backlog Tasks">
                  <Table columns={taskColumns} data={tasks} emptyMessage="No tasks found for this project." />
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
                                className="artifact-item"
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

      case 'prd-backlog':
        return (
          <Card title="Product Requirements & Epics">
            <EmptyState
              title="PRD Compiler View"
              message="Import and review Markdown specs, generate epic maps, and split oversized tasks."
            />
          </Card>
        );

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

      case 'safety':
        return (
          <Card title="Safety Policies">
            {policy ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <h3>Policy Name: {policy.name}</h3>
                <CodeBlock code={JSON.stringify(policy.rules, null, 2)} />
              </div>
            ) : (
              <EmptyState title="No Policy Found" message="Verify default project safety policies." />
            )}
          </Card>
        );

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
