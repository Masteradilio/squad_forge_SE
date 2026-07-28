import { describe, expect, it } from 'vitest';

import type { Task } from '../api/client';
import { wouldCreateCycle } from './taskGraph';

const task = (id: number, dependencies: number[] = []): Task => ({
  id,
  project_id: 1,
  key: `LF-${id}`,
  title: `Task ${id}`,
  description: '',
  status: 'READY',
  dependency_task_ids: dependencies,
});

describe('wouldCreateCycle', () => {
  it('detects transitive dependency cycles', () => {
    expect(wouldCreateCycle(1, [2], [task(1), task(2, [3]), task(3, [1])])).toBe(true);
  });

  it('allows an acyclic dependency chain', () => {
    expect(wouldCreateCycle(1, [2], [task(1), task(2, [3]), task(3)])).toBe(false);
  });
});
