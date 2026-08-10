import React from 'react';

interface CardProps {
  title?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
  onClick?: () => void;
  testId?: string;
  style?: React.CSSProperties;
}

export function Card({ title, actions, children, className = '', onClick, testId, style }: CardProps) {
  return (
    <div
      onClick={onClick}
      data-testid={testId}
      className={`glass rounded-xl p-5 transition-all duration-300 ${
        onClick ? 'cursor-pointer hover:bg-[var(--bg-card-hover)]' : ''
      } ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        borderRadius: '12px',
        ...style,
      }}
    >
      {(title || actions) && (
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderBottom: '1px solid var(--border-color)',
          paddingBottom: '12px',
        }}>
          {title && <h3 style={{ fontSize: '16px', fontWeight: 600 }}>{title}</h3>}
          {actions && <div style={{ display: 'flex', gap: '8px' }}>{actions}</div>}
        </div>
      )}
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  );
}
