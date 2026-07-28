import type { Task } from '../api/client';

export function wouldCreateCycle(
  taskId: number,
  newDependencies: number[],
  allTasks: Task[],
): boolean {
  const tasksById = new Map(allTasks.map((task) => [task.id, task]));
  const visited = new Set<number>();
  const queue = [...newDependencies];
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (current === taskId) return true;
    if (visited.has(current)) continue;
    visited.add(current);
    const task = tasksById.get(current);
    if (task) queue.push(...task.dependency_task_ids);
  }
  return false;
}
