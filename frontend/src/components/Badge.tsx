import type { ReactNode } from 'react';

interface BadgeProps {
  label?: ReactNode;
  children?: ReactNode;
  variant?: 'success' | 'warning' | 'danger' | 'info' | 'primary' | 'muted' | 'blocked';
}

export function Badge({ label, children, variant }: BadgeProps) {
  const getColors = () => {
    switch (variant) {
      case 'success':
        return { color: 'var(--color-success)', bg: 'var(--color-success-bg)' };
      case 'warning':
        return { color: 'var(--color-warning)', bg: 'var(--color-warning-bg)' };
      case 'danger':
        return { color: 'var(--color-danger)', bg: 'var(--color-danger-bg)' };
      case 'info':
        return { color: 'var(--color-info)', bg: 'var(--color-info-bg)' };
      case 'blocked':
        return { color: 'var(--color-blocked)', bg: 'var(--color-blocked-bg)' };
      case 'muted':
        return { color: 'var(--text-muted)', bg: 'rgba(255, 255, 255, 0.05)' };
      case 'primary':
      default:
        return { color: 'var(--color-primary)', bg: 'rgba(120, 80, 255, 0.15)' };
    }
  };

  const { color, bg } = getColors();

  return (
    <span style={{
      display: 'inline-block',
      padding: '4px 8px',
      borderRadius: '6px',
      fontSize: '11px',
      fontWeight: 600,
      textTransform: 'uppercase',
      color,
      backgroundColor: bg,
      border: `1px solid ${color}22`,
      whiteSpace: 'nowrap',
    }}>
      {children ?? label}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toUpperCase();
  let variant: BadgeProps['variant'] = 'primary';

  if (['DONE', 'COMPLETED', 'PR_READY', 'SUCCESS'].includes(normalized)) {
    variant = 'success';
  } else if (['FAILED', 'FAILED_SAFE', 'ERROR'].includes(normalized)) {
    variant = 'danger';
  } else if (['BLOCKED'].includes(normalized)) {
    variant = 'blocked';
  } else if (['PAUSED', 'WARNING'].includes(normalized)) {
    variant = 'warning';
  } else if ([
    'RUNNING', 'CLAIMED', 'PLANNING', 'IMPLEMENTING',
    'TESTING', 'REPAIRING', 'REVIEWING'
  ].includes(normalized)) {
    variant = 'info';
  } else if (['CANCELLED'].includes(normalized)) {
    variant = 'muted';
  }

  return <Badge label={status} variant={variant} />;
}
