import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from './App';

describe('App unified workspace navigation', () => {
  it('renders the unified chat and pipeline workspace and navigates to the remaining menus', async () => {
    window.location.hash = '#/chat';
    render(<App />);

    expect(screen.getByRole('heading', { name: /Do documento ao software entregue/i })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Backlog' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Security Auditor' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Tester final' })).toBeTruthy();

    fireEvent.click(screen.getByText(/Chat \+ Pipeline\/Kanban Workspace/i));
    expect(screen.getByTestId('forge-pipeline-board')).toBeTruthy();

    fireEvent.click(screen.getByText(/3\. Telemetria & OpenTelemetry Tracing/i));
    expect(screen.getByText(/OpenTelemetry Squad Tracing Timeline/i)).toBeTruthy();

    fireEvent.click(screen.getByText(/4\. Skills & Agentes/i));
    expect(screen.getByText(/Editor de Skills & Agentes/i)).toBeTruthy();

    fireEvent.click(screen.getByText(/5\. Modelos \(OmniRoute\)/i));
    expect(screen.getByText(/OmniRoute routing/i)).toBeTruthy();
  });
});
