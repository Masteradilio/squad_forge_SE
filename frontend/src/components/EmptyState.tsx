import React from 'react';

interface EmptyStateProps {
  title: string;
  message?: string;
  action?: React.ReactNode;
}

export function EmptyState({ title, message, action }: EmptyStateProps) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '48px 24px',
      textAlign: 'center',
      background: 'var(--bg-card)',
      border: '1px dashed var(--border-color)',
      borderRadius: '12px',
      gap: '12px',
    }}>
      <h4 style={{
        fontSize: '16px',
        fontWeight: 600,
        color: 'var(--text-primary)',
      }}>{title}</h4>
      {message && (
        <p style={{
          fontSize: '14px',
          color: 'var(--text-secondary)',
          maxWidth: '400px',
        }}>
          {message}
        </p>
      )}
      {action && <div style={{ marginTop: '8px' }}>{action}</div>}
    </div>
  );
}
