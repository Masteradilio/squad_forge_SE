import { useCallback, useEffect, useState } from 'react';
import { apiClient, type Project, type Task } from './api/client';
import { useProjectEvents, type LifecycleEventPayload } from './api/events';
import { Alert } from './components/Alert';
import { AppSidebar, type AppTab } from './components/AppSidebar';
import { ComplianceTestsView } from './components/ComplianceTestsView';
import { ForgeContinuityView } from './components/ForgeContinuityView';
import { KanbanBoard } from './components/KanbanBoard';
import { ModelSettingsView } from './components/ModelSettingsView';
import { MissionControlView } from './components/MissionControlView';
import { OperationsStream } from './components/OperationsStream';
import { POChatView } from './components/POChatView';
import { SkillsEditorView } from './components/SkillsEditorView';
import { TracingTimelineView, type TraceSpanItem } from './components/TracingTimelineView';

const VALID_TABS: readonly AppTab[] = ['chat', 'kanban', 'tests', 'skills', 'references', 'settings'];

function isAppTab(value: string): value is AppTab {
  return VALID_TABS.includes(value as AppTab);
}

export default function App() {
  const [currentTab, setCurrentTab] = useState<AppTab>('chat');
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState<string | null>(null);
  const [telemetrySpans, setTelemetrySpans] = useState<TraceSpanItem[]>([]);
  const [events, setEvents] = useState<LifecycleEventPayload[]>([]);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadProjectData = useCallback(async () => {
    if (!activeProject) {
      setTasks([]);
      setTelemetrySpans([]);
      setTasksLoading(false);
      setTasksError(null);
      return;
    }

    setTasksLoading(true);
    setTasksError(null);
    try {
      const [projectTasks, spans] = await Promise.all([
        apiClient.fetchTasks(activeProject.id),
        apiClient.fetchTelemetrySpans(activeProject.id),
      ]);
      setTasks(projectTasks);
      setTelemetrySpans(spans as TraceSpanItem[]);
      setTasksLoading(false);
      setError(null);
    } catch (err) {
      console.error('Failed to synchronize project data:', err);
      setTasksLoading(false);
      setTasksError(err instanceof Error ? err.message : String(err));
      setError('Não foi possível sincronizar os dados do projeto com o backend.');
    }
  }, [activeProject]);

  const handleLiveEvent = useCallback(
    (event: LifecycleEventPayload) => {
      setEvents((previous) => [event, ...previous].slice(0, 50));
      const reloadEvents = new Set([
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
      ]);
      if (reloadEvents.has(event.event_type)) {
        void loadProjectData();
      }
    },
    [loadProjectData],
  );

  const sseConnected = useProjectEvents(activeProject?.id || 0, handleLiveEvent);

  useEffect(() => {
    const handleHash = () => {
      const hashTab = window.location.hash.replace('#/', '');
      if (isAppTab(hashTab)) {
        setCurrentTab(hashTab);
      }
    };

    window.addEventListener('hashchange', handleHash);
    handleHash();
    return () => window.removeEventListener('hashchange', handleHash);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadProjects = async () => {
      try {
        const data = await apiClient.fetchProjects();
        if (cancelled) return;
        setProjects(data);
        setActiveProject((current) => current && data.some((project) => project.id === current.id)
          ? current
          : data.at(-1) ?? null);
        setBackendHealthy(true);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        console.error('Failed to load projects:', err);
        setBackendHealthy(false);
        setError('Não foi possível conectar ao backend LocalForge OS.');
      }
    };

    void loadProjects();
    const interval = window.setInterval(() => {
      void loadProjects();
    }, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    // Project data is an external resource synchronized by this effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadProjectData();
  }, [loadProjectData]);

  const handleNavigateToTab = (tab: string) => {
    if (isAppTab(tab)) {
      setCurrentTab(tab);
    }
  };

  const handleSelectProject = async (projectId: number) => {
    const existingProject = projects.find((project) => project.id === projectId);
    if (existingProject) {
      setActiveProject(existingProject);
      return;
    }

    try {
      const freshProjects = await apiClient.fetchProjects();
      setProjects(freshProjects);
      setActiveProject(freshProjects.find((project) => project.id === projectId) ?? null);
    } catch (err) {
      console.error('Failed to select project:', err);
    }
  };

  const handleResetAll = () => {
    setProjects([]);
    setActiveProject(null);
    setTasks([]);
    setEvents([]);
  };

  const renderTabContent = () => {
    switch (currentTab) {
      case 'chat':
        return (
          <>
            <MissionControlView projectId={activeProject?.id} liveEvents={events} />
            <POChatView
              activeProject={activeProject}
              onNavigateToTab={handleNavigateToTab}
              onSelectProject={handleSelectProject}
            />
          </>
        );
      case 'kanban':
        return (
          <KanbanBoard
            tasks={tasks}
            activeProjectId={activeProject?.id}
            loading={tasksLoading}
            error={tasksError}
            onRefresh={() => void loadProjectData()}
            onResetAll={handleResetAll}
          />
        );
      case 'tests':
        return (
          <div className="space-y-6">
            <TracingTimelineView spans={telemetrySpans} loading={tasksLoading} error={tasksError} />
            <ComplianceTestsView projectId={activeProject?.id} onNavigateToTab={handleNavigateToTab} />
          </div>
        );
      case 'skills':
        return <SkillsEditorView projectId={activeProject?.id} />;
      case 'references':
        return <ForgeContinuityView projectId={activeProject?.id} />;
      case 'settings':
        return <ModelSettingsView />;
    }
  };

  return (
    <div className="app-shell" data-testid="app-shell" style={{ display: 'flex', minHeight: '100vh', backgroundColor: 'var(--bg-app)' }}>
      <AppSidebar
        projects={projects}
        activeProject={activeProject}
        currentTab={currentTab}
        backendHealthy={backendHealthy}
        sseConnected={sseConnected}
        onProjectChange={setActiveProject}
        onTabChange={setCurrentTab}
      />
      <div className="app-content" style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <main
          className="app-main"
          style={{
            flex: 1,
            padding: '40px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '24px',
          }}
        >
          {error && <Alert type="error">{error}</Alert>}
          {renderTabContent()}
        </main>
        <OperationsStream events={events} />
      </div>
    </div>
  );
}
