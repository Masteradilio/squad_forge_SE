import { useState } from 'react';

interface CodeBlockProps {
  code: string;
  maxHeight?: string;
}

export function CodeBlock({ code, maxHeight = '400px' }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div style={{
      position: 'relative',
      borderRadius: '8px',
      border: '1px solid var(--border-color)',
      background: 'hsl(224, 71%, 2%)',
      overflow: 'hidden',
    }}>
      <button
        onClick={handleCopy}
        style={{
          position: 'absolute',
          right: '8px',
          top: '8px',
          padding: '4px 8px',
          borderRadius: '4px',
          background: 'rgba(255, 255, 255, 0.05)',
          border: '1px solid var(--border-color)',
          color: 'var(--text-secondary)',
          fontSize: '11px',
          cursor: 'pointer',
        }}
      >
        {copied ? 'Copied' : 'Copy'}
      </button>

      <pre style={{
        margin: 0,
        padding: '16px',
        maxHeight,
        overflow: 'auto',
        fontSize: '13px',
        fontFamily: 'monospace, Courier New',
        color: 'var(--text-primary)',
        lineHeight: 1.6,
        textAlign: 'left',
      }}>
        <code>{code}</code>
      </pre>
    </div>
  );
}
