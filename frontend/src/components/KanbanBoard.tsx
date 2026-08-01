import { useState } from 'react';
import type { Task } from '../api/client';
import { StatusBadge } from './Badge';
import { Card } from './Card';
import { Button } from './Button';
import { apiClient } from '../api/client';

interface KanbanBoardProps {
  tasks: Task[];
  activeProjectId?: number;
  onTaskClick?: (task: Task) => void;
  onRefresh?: () => void;
  onStartSquad?: () => void;
}

export interface KanbanColumnConfig {
  id: string;
  title: string;
  statuses: readonly string[];
  color: string;
  wipLimit: number;
}

export const KANBAN_COLUMNS: KanbanColumnConfig[] = [
  { id: 'BACKLOG', title: '1. Backlog de Tarefas', statuses: ['BACKLOG', 'PLANNING'], color: '#6b7280', wipLimit: 10 },
  { id: 'IN_PROGRESS', title: '2. Em Andamento (WIP)', statuses: ['READY', 'CLAIMED', 'IMPLEMENTING', 'TESTING', 'REPAIRING', 'REVIEWING'], color: '#3b82f6', wipLimit: 5 },
  { id: 'BLOCKED', title: '3. Bloqueado (Autocura)', statuses: ['BLOCKED', 'CANCELLED', 'FAILED_SAFE'], color: '#ef4444', wipLimit: 3 },
  { id: 'DONE', title: '4. Finalizado (PR_READY)', statuses: ['PR_READY', 'DONE'], color: '#10b981', wipLimit: 20 },
];

export function tasksForColumn(tasks: Task[], statuses: readonly string[]): Task[] {
  return tasks.filter((task) => statuses.includes(task.status));
}

export function KanbanBoard({ tasks, activeProjectId, onTaskClick, onRefresh, onStartSquad }: KanbanBoardProps) {
  const [rejectModalTask, setRejectModalTask] = useState<Task | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [processingPR, setProcessingPR] = useState(false);
  const [startingSquad, setStartingSquad] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Filter tasks based on search query
  const filteredTasks = tasks.filter(
    (t) =>
      t.key.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const prReadyTasks = tasks.filter((t) => t.status === 'PR_READY');

  const handleStartSquadExecution = async () => {
    if (!activeProjectId) return;
    try {
      setStartingSquad(true);
      await apiClient.startSquad(activeProjectId);
      alert('🚀 Execução da Squad disparada com sucesso! As primeiras tarefas foram movidas para Em Andamento (WIP).');
      onRefresh?.();
    } catch (err: any) {
      alert(`Falha ao iniciar Squad: ${err.message || err}`);
    } finally {
      setStartingSquad(false);
    }
  };

  const handleApprovePR = async (taskId: number) => {
    try {
      setProcessingPR(true);
      await apiClient.approvePR(taskId);
      alert('PR aprovado pelo PO e mergeado na main com sucesso! 🚀');
      onRefresh?.();
    } catch (err) {
      alert(`Falha ao aprovar PR: ${err}`);
    } finally {
      setProcessingPR(false);
    }
  };

  const handleConfirmRejectPR = async () => {
    if (!rejectModalTask || !rejectionReason.trim()) return;
    try {
      setProcessingPR(true);
      await apiClient.rejectPR(rejectModalTask.id, rejectionReason);
      alert(`PR rejeitado. A tarefa retornou para o quadro "Bloqueado" com a observação do PO.`);
      setRejectModalTask(null);
      setRejectionReason('');
      onRefresh?.();
    } catch (err) {
      alert(`Falha ao rejeitar PR: ${err}`);
    } finally {
      setProcessingPR(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header & Filter Bar (Cline Kanban Style) */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: 'var(--bg-secondary)', padding: '16px 20px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 800, margin: 0 }}>📋 Kanban Board & Worktree Isolation</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '4px 0 0 0' }}>
            Orquestração visual da Squad por branch isolada e controle de limite WIP (Work In Progress).
          </p>
        </div>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <Button
            variant="primary"
            onClick={handleStartSquadExecution}
            disabled={startingSquad || !activeProjectId}
            title="Disparar a execução da Squad de Agentes para implementar as tarefas do backlog"
          >
            {startingSquad ? 'Disparando Execução...' : '🚀 Iniciar Execução da Squad'}
          </Button>
          <input
            type="text"
            placeholder="🔍 Filtrar por palavra-chave..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '240px',
              padding: '8px 14px',
              borderRadius: '8px',
              backgroundColor: 'var(--bg-input)',
              border: '1px solid var(--border-color)',
              color: 'var(--text-primary)',
              fontSize: '13px',
            }}
          />
          {searchQuery && (
            <Button variant="secondary" onClick={() => setSearchQuery('')}>Limpar Filtro</Button>
          )}
        </div>
      </div>

      {/* Top 4-Column Board */}
      <div style={{ display: 'flex', gap: '16px', overflowX: 'auto', paddingBottom: '16px', minHeight: '520px' }}>
        {KANBAN_COLUMNS.map((column) => {
          const columnTasks = tasksForColumn(filteredTasks, column.statuses);
          const isExceedingWip = columnTasks.length > column.wipLimit;

          return (
            <div
              key={column.id}
              style={{
                flex: '1 1 280px',
                backgroundColor: 'var(--bg-secondary)',
                padding: '16px',
                borderRadius: '12px',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                border: '1px solid var(--border-color)',
                borderTop: `4px solid ${column.color}`,
              }}
            >
              <h3 style={{ margin: '0 0 8px 0', fontSize: '0.95rem', color: 'var(--text-primary)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>{column.title}</span>
                <span
                  title={`WIP Limit: ${column.wipLimit}`}
                  style={{
                    backgroundColor: isExceedingWip ? '#ef4444' : 'var(--bg-input)',
                    color: isExceedingWip ? '#fff' : 'var(--text-primary)',
                    padding: '2px 10px',
                    borderRadius: '12px',
                    fontSize: '0.8rem',
                    fontWeight: 700,
                    border: '1px solid var(--border-color)',
                  }}
                >
                  {columnTasks.length}/{column.wipLimit}
                </span>
              </h3>

              {columnTasks.map((task) => {
                const isBlocked = task.status === 'BLOCKED';
                const hasPOFeedback = task.description?.includes('[PO REJECTION REASON]');
                const worktreeBranch = `task/${task.key.toLowerCase()}`;

                return (
                  <button
                    type="button"
                    key={task.id}
                    onClick={() => onTaskClick?.(task)}
                    aria-label={`Open task ${task.key}: ${task.title}`}
                    style={{
                      backgroundColor: 'var(--bg-input)',
                      padding: '14px',
                      borderRadius: '8px',
                      boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
                      cursor: onTaskClick ? 'pointer' : 'default',
                      border: '1px solid var(--border-color)',
                      borderLeft: `4px solid ${isBlocked ? '#ef4444' : '#3b82f6'}`,
                      color: 'inherit',
                      textAlign: 'left',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '6px' }}>
                      <span style={{ fontWeight: 700, color: 'var(--color-primary)' }}>{task.key}</span>
                      {hasPOFeedback && <span style={{ color: '#ef4444', fontWeight: 700 }}>⚠️ Feedback PO</span>}
                    </div>

                    <div style={{ fontWeight: '600', marginBottom: '8px', fontSize: '0.95rem' }}>{task.title}</div>

                    {/* Git Worktree Isolation Badge (Cline Kanban Feature) */}
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', backgroundColor: 'rgba(255,255,255,0.03)', padding: '4px 8px', borderRadius: '4px', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '6px', fontFamily: 'monospace' }}>
                      <span>🌿</span>
                      <span>{worktreeBranch}</span>
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <StatusBadge status={task.status} />
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                        {task.risk_level} risk
                      </span>
                    </div>
                  </button>
                );
              })}

              {columnTasks.length === 0 && (
                <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem', padding: '30px 0' }}>
                  Nenhuma tarefa
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Bottom PR Review Section */}
      <Card style={{ padding: '20px', borderTop: '4px solid #10b981' }}>
        <h2 style={{ fontSize: '18px', fontWeight: 700, margin: '0 0 16px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
          🔍 Painel de Revisão & Aprovação de PRs pelo Product Owner
        </h2>

        {prReadyTasks.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {prReadyTasks.map((task) => (
              <div
                key={task.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '16px',
                  backgroundColor: 'var(--bg-input)',
                  borderRadius: '8px',
                  border: '1px solid var(--border-color)',
                }}
              >
                <div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 700 }}>{task.key}</div>
                  <div style={{ fontSize: '15px', fontWeight: 600, margin: '4px 0' }}>{task.title}</div>
                  <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{task.description.slice(0, 100)}...</div>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <Button variant="danger" onClick={() => setRejectModalTask(task)} disabled={processingPR}>
                    ❌ Rejeitar PR (Devolver ao Bloqueado)
                  </Button>
                  <Button variant="success" onClick={() => handleApprovePR(task.id)} disabled={processingPR}>
                    ✅ Aprovar PR (Merge na Main)
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: 'var(--text-muted)', fontSize: '14px', textAlign: 'center', padding: '20px' }}>
            Nenhum Pull Request pendente no momento. As tarefas concluídas pela Squad aparecerão aqui para aprovação do PO.
          </div>
        )}
      </Card>

      {/* Rejection Reason Modal */}
      {rejectModalTask && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <Card style={{ width: '520px', padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h2 style={{ margin: 0, fontSize: '18px', color: '#ef4444' }}>
              ❌ Rejeição de PR: {rejectModalTask.key}
            </h2>
            <p style={{ fontSize: '14px', color: 'var(--text-secondary)', margin: 0 }}>
              Informe o motivo da rejeição. A tarefa retornará ao quadro **Bloqueado** com prioridade máxima para a Squad realizar a correção.
            </p>
            <textarea
              rows={5}
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              placeholder="Descreva exatamente o que não está em conformidade com o seu desejo..."
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '8px',
                backgroundColor: 'var(--bg-input)',
                border: '1px solid var(--border-color)',
                color: '#fff',
                fontSize: '14px',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <Button variant="secondary" onClick={() => setRejectModalTask(null)}>Cancelar</Button>
              <Button variant="danger" onClick={handleConfirmRejectPR} disabled={!rejectionReason.trim() || processingPR}>
                Confirmar Rejeição & Retornar ao Bloqueado
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
