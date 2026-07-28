import type { Project } from '../api/client';

export type AppTab =
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

const TABS: AppTab[] = [
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
];

interface AppSidebarProps {
  projects: Project[];
  activeProject: Project | null;
  currentTab: AppTab;
  backendHealthy: boolean | null;
  sseConnected: boolean;
  onProjectChange: (project: Project) => void;
}

export function AppSidebar({
  projects,
  activeProject,
  currentTab,
  backendHealthy,
  sseConnected,
  onProjectChange,
}: AppSidebarProps) {
  return (
    <aside style={{
      width: 'var(--sidebar-width)',
      backgroundColor: 'var(--bg-sidebar)',
      borderRight: '1px solid var(--border-color)',
      padding: '24px 16px',
      display: 'flex',
      flexDirection: 'column',
      gap: '24px',
      flexShrink: 0,
    }}>
      <h2 style={{ fontSize: '18px', fontWeight: 700, letterSpacing: '0.5px' }}>
        LocalForge OS
      </h2>

      <div>
        <label htmlFor="active-project" style={{
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
            id="active-project"
            value={activeProject?.id || ''}
            onChange={(event) => {
              const project = projects.find(
                (item) => item.id === Number.parseInt(event.target.value, 10),
              );
              if (project) onProjectChange(project);
            }}
            style={{
              width: '100%',
              padding: '10px',
              borderRadius: '8px',
              backgroundColor: 'var(--bg-input)',
              border: '1px solid var(--border-color)',
              color: 'var(--text-primary)',
            }}
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>{project.name}</option>
            ))}
          </select>
        ) : (
          <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No projects</span>
        )}
      </div>

      <nav aria-label="LocalForge sections" style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
        {TABS.map((tab) => {
          const active = currentTab === tab;
          return (
            <a
              key={tab}
              href={`#/${tab}`}
              aria-current={active ? 'page' : undefined}
              style={{
                display: 'block',
                padding: '10px 16px',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: 500,
                color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                backgroundColor: active ? 'var(--color-primary)' : 'transparent',
                textDecoration: 'none',
              }}
            >
              {tab.split('-').map((word) => word[0].toUpperCase() + word.slice(1)).join(' ')}
            </a>
          );
        })}
      </nav>

      <div aria-label="Connection status" style={{
        padding: '12px',
        borderRadius: '8px',
        backgroundColor: 'rgba(255, 255, 255, 0.02)',
        border: '1px solid var(--border-color)',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
      }}>
        <StatusLine label="API Server" healthy={backendHealthy} healthyText="Online" unhealthyText="Offline" />
        <StatusLine label="Live Stream" healthy={sseConnected} healthyText="Subscribed" unhealthyText="Reconnecting" />
      </div>
    </aside>
  );
}

function StatusLine({ label, healthy, healthyText, unhealthyText }: {
  label: string;
  healthy: boolean | null;
  healthyText: string;
  unhealthyText: string;
}) {
  const color = healthy === null
    ? 'var(--text-muted)'
    : healthy ? 'var(--color-success)' : 'var(--color-danger)';
  const statusText = healthy === null ? 'Checking' : healthy ? healthyText : unhealthyText;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px' }}>
      <span aria-hidden="true" style={{
        width: '8px',
        height: '8px',
        borderRadius: '50%',
        backgroundColor: color,
        boxShadow: `0 0 8px ${color}`,
      }} />
      <span>{label}: {statusText}</span>
    </div>
  );
}
