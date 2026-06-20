import React from 'react';

export interface TimelineItem {
  id?: number | string;
  title: string;
  subtitle?: string;
  content?: React.ReactNode;
  time?: string;
  icon?: React.ReactNode;
  type?: 'success' | 'warning' | 'danger' | 'info' | 'primary' | 'muted';
}

interface TimelineProps {
  items: TimelineItem[];
}

export function Timeline({ items }: TimelineProps) {
  if (items.length === 0) {
    return <div style={{ color: 'var(--text-muted)' }}>No events recorded.</div>;
  }

  const getColor = (type?: string) => {
    switch (type) {
      case 'success':
        return 'var(--color-success)';
      case 'warning':
        return 'var(--color-warning)';
      case 'danger':
        return 'var(--color-danger)';
      case 'info':
        return 'var(--color-info)';
      case 'primary':
        return 'var(--color-primary)';
      case 'muted':
      default:
        return 'var(--text-muted)';
    }
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '24px',
      position: 'relative',
      paddingLeft: '24px',
      borderLeft: '1px solid var(--border-color)',
    }}>
      {items.map((item, index) => {
        const dotColor = getColor(item.type);
        return (
          <div key={item.id || index} style={{ position: 'relative' }}>
            <div style={{
              position: 'absolute',
              left: '-29px',
              top: '4px',
              width: '9px',
              height: '9px',
              borderRadius: '50%',
              backgroundColor: dotColor,
              border: `2px solid var(--bg-app)`,
              boxShadow: `0 0 8px ${dotColor}`,
            }} />
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}>
                <span style={{ fontWeight: 600, fontSize: '14px' }}>{item.title}</span>
                {item.time && (
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    {item.time}
                  </span>
                )}
              </div>
              {item.subtitle && (
                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  {item.subtitle}
                </span>
              )}
              {item.content && (
                <div style={{
                  marginTop: '8px',
                  fontSize: '13px',
                  color: 'var(--text-secondary)',
                }}>
                  {item.content}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
