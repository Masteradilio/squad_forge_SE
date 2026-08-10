import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiClient, type ActionApproval } from '../api/client';
import { MissionControlView } from './MissionControlView';

const pendingApproval: ActionApproval = {
  id: 42,
  project_id: 7,
  kind: 'RUN_COMMAND',
  payload: { command: 'npm test' },
  status: 'PENDING',
  created_at: '2026-08-07T12:00:00Z',
};

function mockMissionControlResources(approvals: ActionApproval[] = [pendingApproval]) {
  vi.spyOn(apiClient, 'fetchTasks').mockResolvedValue([]);
  vi.spyOn(apiClient, 'fetchRuns').mockResolvedValue([]);
  vi.spyOn(apiClient, 'fetchAgents').mockResolvedValue([]);
  vi.spyOn(apiClient, 'fetchMemoryFacts').mockResolvedValue([]);
  vi.spyOn(apiClient, 'fetchPendingApprovals').mockResolvedValue(approvals);
  vi.spyOn(apiClient, 'fetchTelemetryEvents').mockResolvedValue([]);
}

async function renderPendingApproval() {
  mockMissionControlResources();
  render(<MissionControlView projectId={7} liveEvents={[]} />);
  await screen.findByTestId('safety-approval-42');
}

describe('MissionControlView safety approvals', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('lists a pending approval and updates the UI after approval', async () => {
    const decideApproval = vi.spyOn(apiClient, 'decideApproval').mockImplementation(async (approvalId, action) => ({
      ...pendingApproval,
      id: approvalId,
      status: action === 'approve' ? 'APPROVED' : 'REJECTED',
    }));

    await renderPendingApproval();

    expect(screen.getByRole('button', { name: 'Aprovar aprovação 42' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Rejeitar aprovação 42' })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Aprovar aprovação 42' }));

    await waitFor(() => expect(decideApproval).toHaveBeenCalledWith(42, 'approve'));
    expect((await screen.findByTestId('safety-decision-result')).textContent).toContain('APPROVED');
    expect(screen.queryByTestId('safety-approval-42')).toBeNull();
  });

  it('updates the UI after rejection and keeps the decision visible', async () => {
    const decideApproval = vi.spyOn(apiClient, 'decideApproval').mockImplementation(async (approvalId, action) => ({
      ...pendingApproval,
      id: approvalId,
      status: action === 'approve' ? 'APPROVED' : 'REJECTED',
    }));

    await renderPendingApproval();
    fireEvent.click(screen.getByRole('button', { name: 'Rejeitar aprovação 42' }));

    await waitFor(() => expect(decideApproval).toHaveBeenCalledWith(42, 'reject'));
    expect((await screen.findByTestId('safety-decision-result')).textContent).toContain('REJECTED');
    expect(screen.queryByTestId('safety-approval-42')).toBeNull();
  });

  it('shows a visible error when the decision endpoint fails', async () => {
    vi.spyOn(apiClient, 'decideApproval').mockRejectedValue(new Error('approval endpoint unavailable'));

    await renderPendingApproval();
    fireEvent.click(screen.getByRole('button', { name: 'Aprovar aprovação 42' }));

    expect((await screen.findByTestId('safety-decision-error')).textContent).toContain('approval endpoint unavailable');
    expect(screen.getByTestId('safety-approval-42')).toBeTruthy();
  });
});
