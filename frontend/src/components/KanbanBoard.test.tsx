import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { Task } from '../api/client';
import { KanbanBoard, tasksForColumn } from './KanbanBoard';

function task(overrides: Partial<Task>): Task {
  return {
    id: 1,
    project_id: 1,
    key: 'LF-1',
    title: 'Example task',
    description: '',
    status: 'READY',
    risk_level: 'low',
    metadata: {},
    ...overrides,
  } as Task;
}

describe('KanbanBoard', () => {
  it('groups tasks without changing their runtime status', () => {
    const tasks = [task({ status: 'READY' }), task({ id: 2, status: 'PR_READY' })];

    expect(tasksForColumn(tasks, ['REVIEWING', 'PR_READY'])).toEqual([tasks[1]]);
    expect(tasks[1].status).toBe('PR_READY');
  });

  it('opens a task through an accessible button', () => {
    const onTaskClick = vi.fn();
    const item = task({ key: 'LF-42', title: 'Add audit gate' });

    render(<KanbanBoard tasks={[item]} onTaskClick={onTaskClick} />);
    fireEvent.click(screen.getByRole('button', { name: /open task lf-42/i }));

    expect(onTaskClick).toHaveBeenCalledWith(item);
  });
});
