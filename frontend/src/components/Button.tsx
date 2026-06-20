import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'warning' | 'success' | 'ghost';
  loading?: boolean;
  children: React.ReactNode;
}

export function Button({
  variant = 'primary',
  loading = false,
  children,
  style,
  disabled,
  ...props
}: ButtonProps) {
  const getColors = () => {
    switch (variant) {
      case 'secondary':
        return {
          bg: 'rgba(255, 255, 255, 0.05)',
          color: 'var(--text-primary)',
          border: '1px solid var(--border-color)',
        };
      case 'danger':
        return {
          bg: 'var(--color-danger-bg)',
          color: 'var(--color-danger)',
          border: '1px solid hsla(0, 84%, 60%, 0.3)',
        };
      case 'warning':
        return {
          bg: 'var(--color-warning-bg)',
          color: 'var(--color-warning)',
          border: '1px solid hsla(38, 92%, 50%, 0.3)',
        };
      case 'success':
        return {
          bg: 'var(--color-success-bg)',
          color: 'var(--color-success)',
          border: '1px solid hsla(142, 70%, 45%, 0.3)',
        };
      case 'ghost':
        return {
          bg: 'transparent',
          color: 'var(--text-secondary)',
          border: '1px solid transparent',
        };
      case 'primary':
      default:
        return {
          bg: 'var(--color-primary)',
          color: 'var(--text-primary)',
          border: '1px solid var(--color-primary)',
        };
    }
  };

  const colors = getColors();

  return (
    <button
      disabled={disabled || loading}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '8px',
        padding: '8px 16px',
        borderRadius: '8px',
        fontSize: '14px',
        fontWeight: 500,
        cursor: disabled || loading ? 'not-allowed' : 'pointer',
        opacity: disabled || loading ? 0.6 : 1,
        transition: 'all 0.2s ease-in-out',
        background: colors.bg,
        color: colors.color,
        border: colors.border,
        ...style,
      }}
      {...props}
    >
      {loading && (
        <span style={{
          width: '12px',
          height: '12px',
          border: '2px solid currentColor',
          borderTopColor: 'transparent',
          borderRadius: '50%',
        }} />
      )}
      {children}
    </button>
  );
}
