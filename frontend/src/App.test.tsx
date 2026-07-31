import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from './App';

describe('App 5-Menu Navigation Router', () => {
  it('renders PO Chat View by default and navigates to all 5 core menus', async () => {
    window.location.hash = '#/chat';
    render(<App />);

    // Menu 1 default: PO Chat
    expect(screen.getByText(/Mission Control & PO Chat/i)).toBeTruthy();

    // Menu 2: Kanban & Revisão de PRs
    fireEvent.click(screen.getByText(/2. Kanban & Revisão de PRs/i));
    expect(screen.getByText(/Painel de Revisão & Aprovação de PRs/i)).toBeTruthy();

    // Menu 3: Testes de Conformidade
    fireEvent.click(screen.getByText(/3. Testes de Conformidade/i));
    expect(screen.getByText(/Testes de Conformidade Pós-Merge/i)).toBeTruthy();

    // Menu 4: Skills & Agentes
    fireEvent.click(screen.getByText(/4. Skills & Agentes/i));
    expect(screen.getByText(/Editor de Skills & Agentes/i)).toBeTruthy();

    // Menu 5: Modelos & Ambiente (.env)
    fireEvent.click(screen.getByText(/5. Modelos & Ambiente \(\.env\)/i));
    expect(screen.getByText(/Configurações de Modelos & Ambiente \(\.env\)/i)).toBeTruthy();
  });
});
