import type { ReactNode } from 'react';

export type ResourceStatus = 'loading' | 'ready' | 'empty' | 'error' | 'blocked';

interface ResourceStateProps {
  status: Exclude<ResourceStatus, 'ready'>;
  title: string;
  message: string;
  action?: ReactNode;
  testId?: string;
}

const STATUS_COLORS: Record<Exclude<ResourceStatus, 'ready'>, string> = {
  loading: 'var(--color-info)',
  empty: 'var(--text-muted)',
  error: 'var(--color-danger)',
  blocked: 'var(--color-warning)',
};

export function ResourceState({ status, title, message, action, testId }: ResourceStateProps) {
  return (
    <div
      role={status === 'error' ? 'alert' : 'status'}
      data-testid={testId ?? `resource-state-${status}`}
      data-resource-state={status}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        padding: '18px',
        borderRadius: '10px',
        border: `1px dashed ${STATUS_COLORS[status]}66`,
        backgroundColor: 'var(--bg-input)',
        color: 'var(--text-secondary)',
      }}
    >
      <strong style={{ color: STATUS_COLORS[status], fontSize: '14px' }}>{title}</strong>
      <span style={{ fontSize: '13px' }}>{message}</span>
      {action && <div style={{ marginTop: '6px' }}>{action}</div>}
    </div>
  );
}
