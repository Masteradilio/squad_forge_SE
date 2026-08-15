import { describe, expect, it } from 'vitest';
import { stageForTask } from './ForgeWorkspaceView';

const task = (status: string) => ({
  id: 10,
  project_id: 1,
  key: 'TASK-10',
  title: 'Entrega de referencia',
  description: '',
  status,
  dependency_task_ids: [],
});

describe('ForgeWorkspaceView pipeline mapping', () => {
  it('maps execution lifecycle statuses into the unified lanes', () => {
    expect(stageForTask(task('BACKLOG'), [])).toBe('backlog');
    expect(stageForTask(task('PLANNING'), [])).toBe('backlog');
    expect(stageForTask(task('IMPLEMENTING'), [])).toBe('execution');
    expect(stageForTask(task('REPAIRING'), [])).toBe('execution');
    expect(stageForTask(task('PR_READY'), [])).toBe('pr');
  });

  it('keeps post-merge quality gates visible before final acceptance', () => {
    expect(stageForTask(task('DONE'), [{
      project_id: 1,
      event_type: 'security.audit.finished',
      payload: { task_id: 10, role: 'Security Auditor' },
      created_at: '2026-08-11T12:00:00Z',
    }])).toBe('security');

    expect(stageForTask(task('DONE'), [{
      project_id: 1,
      event_type: 'test.finished',
      payload: { task_id: 10, role: 'E2E Tester' },
      created_at: '2026-08-11T12:00:00Z',
    }])).toBe('tester');
  });
});
