import { useCallback, useEffect, useState } from 'react';
import { apiClient, type Project, type Task } from './api/client';
import { useProjectEvents, type LifecycleEventPayload } from './api/events';
import { Alert } from './components/Alert';
import { AppSidebar, type AppTab } from './components/AppSidebar';
import { ComplianceTestsView } from './components/ComplianceTestsView';
import { ForgeContinuityView } from './components/ForgeContinuityView';
import { ForgeWorkspaceView } from './components/ForgeWorkspaceView';
import { ModelSettingsView } from './components/ModelSettingsView';
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
      setEvents([]);
      setTasksLoading(false);
      setTasksError(null);
      return;
    }

    setTasksLoading(true);
    setTasksError(null);
    try {
      const [projectTasks, spans, persistedEvents] = await Promise.all([
        apiClient.fetchTasks(activeProject.id),
        apiClient.fetchTelemetrySpans(activeProject.id),
        apiClient.fetchTelemetryEvents(activeProject.id),
      ]);
      setTasks(projectTasks);
      setTelemetrySpans(spans as TraceSpanItem[]);
      setEvents((previous) => {
        const merged = [...(persistedEvents as LifecycleEventPayload[]), ...previous];
        const seen = new Set<string>();
        return merged.filter((item) => {
          const key = String(item.id ?? '') + '|' + item.event_type + '|' + String(item.created_at ?? '');
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        }).slice(0, 200);
      });
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
        setCurrentTab(hashTab === 'kanban' ? 'chat' : hashTab);
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
      setCurrentTab(tab === 'kanban' ? 'chat' : tab);
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

  const renderTabContent = () => {
    switch (currentTab) {
      case 'chat':
      case 'kanban':
        return (
          <ForgeWorkspaceView
            activeProject={activeProject}
            tasks={tasks}
            events={events}
            telemetrySpans={telemetrySpans}
            loading={tasksLoading}
            error={tasksError}
            onRefresh={() => void loadProjectData()}
            onSelectProject={(projectId) => void handleSelectProject(projectId)}
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
      </div>
    </div>
  );
}
