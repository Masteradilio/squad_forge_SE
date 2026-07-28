import type { Task } from '../api/client';
import { StatusBadge } from './Badge';

interface KanbanBoardProps {
  tasks: Task[];
  onTaskClick?: (task: Task) => void;
}

export const KANBAN_COLUMNS = [
  { id: 'BACKLOG', title: 'Backlog', statuses: ['BACKLOG', 'PLANNING'] },
  { id: 'READY', title: 'Ready', statuses: ['READY', 'CLAIMED'] },
  { id: 'IN_PROGRESS', title: 'In Progress', statuses: ['IMPLEMENTING', 'TESTING', 'REPAIRING'] },
  { id: 'REVIEW', title: 'Review', statuses: ['REVIEWING', 'PR_READY'] },
  { id: 'DONE', title: 'Done', statuses: ['DONE', 'CANCELLED', 'FAILED_SAFE'] },
] as const;

export function tasksForColumn(tasks: Task[], statuses: readonly string[]): Task[] {
  return tasks.filter((task) => statuses.includes(task.status));
}

export function KanbanBoard({ tasks, onTaskClick }: KanbanBoardProps) {
  return (
    <div style={{ display: 'flex', gap: '16px', overflowX: 'auto', paddingBottom: '16px', minHeight: '600px' }}>
      {KANBAN_COLUMNS.map((column) => {
        const columnTasks = tasksForColumn(tasks, column.statuses);
        return (
          <div key={column.id} style={{ flex: '0 0 300px', backgroundColor: '#f3f4f6', padding: '16px', borderRadius: '8px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '1.1rem', color: '#374151', display: 'flex', justifyContent: 'space-between' }}>
              {column.title} <span style={{ backgroundColor: '#e5e7eb', padding: '2px 8px', borderRadius: '12px', fontSize: '0.8rem' }}>{columnTasks.length}</span>
            </h3>
            {columnTasks.map((task) => {
              const contract = task.metadata?.task_contract as { seniority_class?: string } | undefined;
              const isChief = contract?.seniority_class === 'chief_only' || contract?.seniority_class === 'chief_led';
              return (
                <button
                  type="button"
                  key={task.id}
                  onClick={() => onTaskClick?.(task)}
                  aria-label={`Open task ${task.key}: ${task.title}`}
                  style={{
                    backgroundColor: 'white',
                    padding: '12px',
                    borderRadius: '6px',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                    cursor: onTaskClick ? 'pointer' : 'default',
                    border: 'none',
                    borderLeft: `4px solid ${isChief ? '#8b5cf6' : '#3b82f6'}`,
                    color: 'inherit',
                    textAlign: 'left',
                  }}
                >
                  <div style={{ fontSize: '0.8rem', color: '#6b7280', marginBottom: '4px' }}>{task.key}</div>
                  <div style={{ fontWeight: '500', marginBottom: '8px', fontSize: '0.95rem' }}>{task.title}</div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <StatusBadge status={task.status} />
                    <span title={isChief ? 'API Model (Chief Engineer)' : 'Local Model'} style={{ fontSize: '0.8rem' }}>
                      {isChief ? 'API' : 'Local'}
                    </span>
                  </div>
                </button>
              );
            })}
            {columnTasks.length === 0 && (
              <div style={{ textAlign: 'center', color: '#9ca3af', fontSize: '0.9rem', padding: '20px 0' }}>
                No tasks
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
