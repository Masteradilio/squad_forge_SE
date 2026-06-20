import React from 'react';

interface AlertProps {
  type?: 'error' | 'warning' | 'info' | 'success';
  title?: string;
  children: React.ReactNode;
}

export function Alert({ type = 'info', title, children }: AlertProps) {
  const getStyles = () => {
    switch (type) {
      case 'error':
        return {
          color: 'var(--color-danger)',
          bg: 'var(--color-danger-bg)',
          border: 'hsla(0, 84%, 60%, 0.25)',
        };
      case 'warning':
        return {
          color: 'var(--color-warning)',
          bg: 'var(--color-warning-bg)',
          border: 'hsla(38, 92%, 50%, 0.25)',
        };
      case 'success':
        return {
          color: 'var(--color-success)',
          bg: 'var(--color-success-bg)',
          border: 'hsla(142, 70%, 45%, 0.25)',
        };
      case 'info':
      default:
        return {
          color: 'var(--color-info)',
          bg: 'var(--color-info-bg)',
          border: 'hsla(199, 89%, 48%, 0.25)',
        };
    }
  };

  const { color, bg, border } = getStyles();

  return (
    <div style={{
      padding: '14px 16px',
      borderRadius: '8px',
      backgroundColor: bg,
      border: `1px solid ${border}`,
      color: 'var(--text-primary)',
      fontSize: '14px',
      display: 'flex',
      flexDirection: 'column',
      gap: '4px',
    }}>
      {title && (
        <span style={{
          fontWeight: 600,
          color,
          fontSize: '14px',
        }}>
          {title}
        </span>
      )}
      <div style={{ color: 'var(--text-secondary)' }}>{children}</div>
    </div>
  );
}
