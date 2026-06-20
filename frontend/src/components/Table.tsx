import React from 'react';

export interface Column<T> {
  header: string;
  accessor: (row: T) => React.ReactNode;
  align?: 'left' | 'center' | 'right';
  width?: string;
}

interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  emptyMessage?: string;
}

export function Table<T>({
  columns,
  data,
  emptyMessage = 'No data available',
}: TableProps<T>) {
  if (data.length === 0) {
    return (
      <div style={{
        padding: '24px',
        textAlign: 'center',
        color: 'var(--text-muted)',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
        background: 'var(--bg-card)'
      }}>
        {emptyMessage}
      </div>
    );
  }

  return (
    <div style={{ overflowX: 'auto', width: '100%' }}>
      <table style={{
        width: '100%',
        borderCollapse: 'collapse',
        textAlign: 'left',
        fontSize: '14px',
      }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
            {columns.map((col, index) => (
              <th
                key={index}
                style={{
                  padding: '12px 16px',
                  color: 'var(--text-secondary)',
                  fontWeight: 500,
                  width: col.width,
                  textAlign: col.align || 'left',
                }}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, rIndex) => (
            <tr
              key={rIndex}
              style={{
                borderBottom: '1px solid var(--border-color)',
              }}
            >
              {columns.map((col, cIndex) => (
                <td
                  key={cIndex}
                  style={{
                    padding: '14px 16px',
                    textAlign: col.align || 'left',
                  }}
                >
                  {col.accessor(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
