import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AppSidebar } from './AppSidebar';

describe('AppSidebar', () => {
  afterEach(() => {
    cleanup();
  });

  it('keeps API health distinct from an offline backend while checking', () => {
    render(
      <AppSidebar
        projects={[]}
        activeProject={null}
        currentTab="chat"
        backendHealthy={null}
        sseConnected={false}
        onProjectChange={vi.fn()}
      />,
    );

    expect(screen.getByText('API Server: Checking')).toBeTruthy();
    expect(screen.getByText('Live Stream: Checking')).toBeTruthy();
  });

  it.each(['chat', 'kanban'] as const)('highlights the unified workspace for the %s tab', (currentTab) => {
    render(
      <AppSidebar
        projects={[]}
        activeProject={null}
        currentTab={currentTab}
        backendHealthy={null}
        sseConnected={false}
        onProjectChange={vi.fn()}
      />,
    );

    const workspaceLink = screen.getByTestId('nav-chat');
    expect(workspaceLink.textContent).toContain('Chat + Pipeline/Kanban');
    expect(workspaceLink.getAttribute('aria-current')).toBe('page');
    expect(screen.queryByTestId('nav-kanban')).toBeNull();
  });
});
