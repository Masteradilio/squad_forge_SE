import type { Project } from '../api/client';

export type AppTab =
  | 'chat'
  | 'kanban'
  | 'tests'
  | 'skills'
  | 'settings';

export const CORE_MENUS: { id: AppTab; label: string; icon: string }[] = [
  { id: 'chat', label: '1. PO Chat & Mission Control', icon: '💬' },
  { id: 'kanban', label: '2. Kanban & Revisão de PRs', icon: '📋' },
  { id: 'tests', label: '3. Testes de Conformidade', icon: '🧪' },
  { id: 'skills', label: '4. Skills & Agentes', icon: '🧩' },
  { id: 'settings', label: '5. Modelos & Ambiente (.env)', icon: '⚙️' },
];

interface AppSidebarProps {
  projects: Project[];
  activeProject: Project | null;
  currentTab: AppTab;
  backendHealthy: boolean | null;
  sseConnected: boolean;
  onProjectChange: (project: Project) => void;
  onTabChange?: (tab: AppTab) => void;
}

export function AppSidebar({
  projects,
  activeProject,
  currentTab,
  backendHealthy,
  sseConnected,
  onProjectChange,
  onTabChange,
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
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{
          width: '32px',
          height: '32px',
          borderRadius: '8px',
          backgroundColor: 'var(--color-primary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 'bold',
          color: '#fff',
        }}>
          LF
        </div>
        <h1 style={{ fontSize: '18px', fontWeight: 800, margin: 0, letterSpacing: '-0.02em' }}>
          LocalForge OS
        </h1>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <label htmlFor="active-project-select" style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
          Active Project
        </label>
        <select
          id="active-project-select"
          aria-label="Active Project"
          value={activeProject?.id || ''}
          onChange={(e) => {
            const proj = projects.find((p) => p.id === Number(e.target.value));
            if (proj) onProjectChange(proj);
          }}
          style={{
            width: '100%',
            padding: '8px 12px',
            borderRadius: '6px',
            backgroundColor: 'var(--bg-input)',
            border: '1px solid var(--border-color)',
            color: 'var(--text-primary)',
            fontSize: '13px',
          }}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
          {projects.length === 0 && <option value="">No projects</option>}
        </select>
      </div>

      <nav aria-label="LocalForge sections" style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
        {CORE_MENUS.map((menu) => {
          const active = currentTab === menu.id;
          return (
            <a
              key={menu.id}
              href={`#/${menu.id}`}
              onClick={(e) => {
                onTabChange?.(menu.id);
              }}
              aria-current={active ? 'page' : undefined}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '12px 16px',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: active ? 700 : 500,
                color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                backgroundColor: active ? 'var(--color-primary)' : 'transparent',
                textDecoration: 'none',
              }}
            >
              <span>{menu.icon}</span>
              <span>{menu.label}</span>
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
