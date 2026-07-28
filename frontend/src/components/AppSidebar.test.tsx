import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AppSidebar } from './AppSidebar';

describe('AppSidebar', () => {
  it('keeps API health distinct from an offline backend while checking', () => {
    render(
      <AppSidebar
        projects={[]}
        activeProject={null}
        currentTab="mission-control"
        backendHealthy={null}
        sseConnected={false}
        onProjectChange={vi.fn()}
      />,
    );

    expect(screen.getByText('API Server: Checking')).toBeTruthy();
    expect(screen.getByText('Live Stream: Reconnecting')).toBeTruthy();
  });
});
