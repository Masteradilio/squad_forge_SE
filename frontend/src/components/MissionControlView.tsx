import { useCallback, useEffect, useState } from 'react';
import {
  apiClient,
  type Agent,
  type ActionApproval,
  type MemoryFact,
  type Run,
  type Task,
} from '../api/client';
import type { LifecycleEventPayload } from '../api/events';
import { Badge, StatusBadge } from './Badge';
import { Card } from './Card';
import { ResourceState, type ResourceStatus } from './ResourceState';

interface MissionControlViewProps {
  projectId?: number;
  liveEvents: LifecycleEventPayload[];
}

interface ListResource<T> {
  status: ResourceStatus;
  data: T[];
  error?: string;
}

interface ApprovalDecisionResult {
  approval: ActionApproval;
  action: 'approve' | 'reject';
}

interface MissionControlData {
  tasks: ListResource<Task>;
  runs: ListResource<Run>;
  agents: ListResource<Agent>;
  memory: ListResource<MemoryFact>;
  safety: ListResource<ActionApproval>;
  timeline: ListResource<unknown>;
}

const blockedResource = <T,>(): ListResource<T> => ({ status: 'blocked', data: [] });

const initialData: MissionControlData = {
  tasks: blockedResource(),
  runs: blockedResource(),
  agents: blockedResource(),
  memory: blockedResource(),
  safety: blockedResource(),
  timeline: blockedResource(),
};

function resourceFromResult<T>(
  result: PromiseSettledResult<T[]>,
  resourceName: string,
): ListResource<T> {
  if (result.status === 'fulfilled') {
    return { status: result.value.length === 0 ? 'empty' : 'ready', data: result.value };
  }

  return {
    status: 'error',
    data: [],
    error: `${resourceName}: ${result.reason instanceof Error ? result.reason.message : String(result.reason)}`,
  };
}

function formatDate(value?: string) {
  if (!value) return 'sem data';
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString();
}

function resourceMessage(resource: ListResource<unknown>, blockedMessage: string) {
  switch (resource.status) {
    case 'loading':
      return { title: 'Carregando dados reais', message: 'Consultando a API do projeto...' };
    case 'empty':
      return { title: 'Nenhum dado retornado', message: 'A API respondeu sem registros para esta área.' };
    case 'error':
      return { title: 'Erro ao consultar a API', message: resource.error ?? 'A resposta não pôde ser lida.' };
    case 'blocked':
      return { title: 'Aguardando projeto', message: blockedMessage };
    case 'ready':
      return null;
  }
}

function PanelState<T>({ resource, blockedMessage, testId }: {
  resource: ListResource<T>;
  blockedMessage: string;
  testId: string;
}) {
  const state = resourceMessage(resource as ListResource<unknown>, blockedMessage);
  if (!state || resource.status === 'ready') return null;
  return <ResourceState status={resource.status} title={state.title} message={state.message} testId={testId} />;
}

export function MissionControlView({ projectId, liveEvents }: MissionControlViewProps) {
  const [data, setData] = useState<MissionControlData>(initialData);
  const [decisionInFlight, setDecisionInFlight] = useState<number | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [decisionResult, setDecisionResult] = useState<ApprovalDecisionResult | null>(null);

  const loadData = useCallback(async () => {
    if (!projectId) {
      setData(initialData);
      return;
    }

    setData({
      tasks: { status: 'loading', data: [] },
      runs: { status: 'loading', data: [] },
      agents: { status: 'loading', data: [] },
      memory: { status: 'loading', data: [] },
      safety: { status: 'loading', data: [] },
      timeline: { status: 'loading', data: [] },
    });

    const results = await Promise.allSettled([
      apiClient.fetchTasks(projectId),
      apiClient.fetchRuns(projectId),
      apiClient.fetchAgents(),
      apiClient.fetchMemoryFacts(projectId),
      apiClient.fetchPendingApprovals(projectId),
      apiClient.fetchTelemetryEvents(projectId),
    ]);

    setData({
      tasks: resourceFromResult(results[0], 'Tarefas'),
      runs: resourceFromResult(results[1], 'Runs'),
      agents: resourceFromResult(results[2], 'Agentes'),
      memory: resourceFromResult(results[3], 'Memória'),
      safety: resourceFromResult(results[4], 'Segurança'),
      timeline: resourceFromResult(results[5], 'Timeline'),
    });
  }, [projectId]);

  useEffect(() => {
    // This effect synchronizes the dashboard with external API state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadData();
    const interval = window.setInterval(() => void loadData(), 5000);
    return () => window.clearInterval(interval);
  }, [loadData]);

  const handleApprovalDecision = async (approvalId: number, action: 'approve' | 'reject') => {
    setDecisionInFlight(approvalId);
    setDecisionError(null);

    try {
      const approval = await apiClient.decideApproval(approvalId, action);
      setData((current) => {
        const remaining = current.safety.data.filter((item) => item.id !== approval.id);
        return {
          ...current,
          safety: {
            ...current.safety,
            status: remaining.length > 0 ? 'ready' : 'empty',
            data: remaining,
            error: undefined,
          },
        };
      });
      setDecisionResult({ approval, action });
    } catch (error) {
      setDecisionError(error instanceof Error ? error.message : String(error));
    } finally {
      setDecisionInFlight(null);
    }
  };

  const taskCounts = data.tasks.data.reduce<Record<string, number>>((counts, task) => {
    counts[task.status] = (counts[task.status] ?? 0) + 1;
    return counts;
  }, {});
  const latestRun = [...data.runs.data].sort((a, b) => {
    const aTime = a.started_at ? new Date(a.started_at).getTime() : a.id;
    const bTime = b.started_at ? new Date(b.started_at).getTime() : b.id;
    return bTime - aTime;
  })[0];
  const timelineItems = [...liveEvents, ...data.timeline.data].slice(0, 12);

  return (
    <section data-testid="mission-control" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <h1 style={{ fontSize: '24px', fontWeight: 800, margin: 0 }}>Mission Control</h1>
        <p style={{ color: 'var(--text-secondary)', marginTop: '4px', fontSize: '14px' }}>
          Estado operacional obtido do control plane LocalForge OS.
        </p>
      </div>

      <div data-testid="mission-control-task-summary" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px' }}>
        <MetricCard label="Total de tarefas" value={data.tasks.data.length} resource={data.tasks} />
        <MetricCard label="Em andamento" value={Object.entries(taskCounts).filter(([status]) => ['READY', 'CLAIMED', 'IMPLEMENTING', 'TESTING', 'REPAIRING', 'REVIEWING'].includes(status)).reduce((total, [, count]) => total + count, 0)} resource={data.tasks} />
        <MetricCard label="Bloqueadas" value={Object.entries(taskCounts).filter(([status]) => ['BLOCKED', 'FAILED_SAFE', 'CANCELLED'].includes(status)).reduce((total, [, count]) => total + count, 0)} resource={data.tasks} />
        <MetricCard label="PR ready" value={taskCounts.PR_READY ?? 0} resource={data.tasks} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
        <Card title="Run atual" testId="mission-control-run">
          <PanelState resource={data.runs} blockedMessage="Selecione um projeto para consultar runs." testId="mission-control-run-state" />
          {data.runs.status === 'ready' && latestRun && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                <strong>Run #{latestRun.id}</strong>
                <StatusBadge status={latestRun.status} />
              </div>
              <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Modo: {latestRun.mode}</span>
              <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Início: {formatDate(latestRun.started_at)}</span>
            </div>
          )}
        </Card>

        <Card title="Agent fleet" testId="mission-control-agents">
          <PanelState resource={data.agents} blockedMessage="Selecione um projeto para consultar o estado dos agentes." testId="mission-control-agents-state" />
          {data.agents.status === 'ready' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {data.agents.data.map((agent) => (
                <div key={agent.id} style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center' }}>
                  <span><strong>{agent.name}</strong><br /><small style={{ color: 'var(--text-secondary)' }}>{agent.role}</small></span>
                  <StatusBadge status={agent.status} />
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Memória do projeto" testId="mission-control-memory">
          <PanelState resource={data.memory} blockedMessage="Selecione um projeto para consultar a memória persistida." testId="mission-control-memory-state" />
          {data.memory.status === 'ready' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <Badge variant="info">{data.memory.data.length} fatos persistidos</Badge>
              {data.memory.data.slice(0, 3).map((fact) => (
                <div key={fact.id} style={{ fontSize: '13px' }}>
                  <strong>{fact.kind}</strong>: {fact.fact}
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Safety center" testId="mission-control-safety">
          <PanelState resource={data.safety} blockedMessage="Selecione um projeto para consultar aprovações de segurança." testId="mission-control-safety-state" />
          {data.safety.status === 'ready' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <Badge variant="warning">{data.safety.data.length} aprovações pendentes</Badge>
              <div
                data-testid="safety-pending-approvals"
                role="list"
                aria-label="Aprovações pendentes"
                style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}
              >
                {data.safety.data.map((approval) => {
                  return (
                    <div
                      key={approval.id}
                      data-testid={`safety-approval-${approval.id}`}
                      role="listitem"
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '8px',
                        padding: '12px',
                        borderRadius: '8px',
                        border: '1px solid var(--border-color)',
                        backgroundColor: 'var(--bg-input)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'center' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                          <strong>{approval.kind}</strong>
                          <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>Aprovação #{approval.id}</span>
                        </div>
                        <StatusBadge status={approval.status} />
                      </div>
                      <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>
                        Criada em {formatDate(approval.created_at)}
                      </span>
                      <div
                        role="group"
                        aria-label={`Decisão da aprovação ${approval.id}`}
                        style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}
                      >
                        <button
                          type="button"
                          aria-label={`Aprovar aprovação ${approval.id}`}
                          onClick={() => void handleApprovalDecision(approval.id, 'approve')}
                          disabled={decisionInFlight !== null}
                          style={{
                            border: '1px solid var(--color-success)',
                            borderRadius: '6px',
                            padding: '7px 10px',
                            color: 'var(--color-success)',
                            backgroundColor: 'transparent',
                            cursor: decisionInFlight === null ? 'pointer' : 'not-allowed',
                          }}
                        >
                          Aprovar
                        </button>
                        <button
                          type="button"
                          aria-label={`Rejeitar aprovação ${approval.id}`}
                          onClick={() => void handleApprovalDecision(approval.id, 'reject')}
                          disabled={decisionInFlight !== null}
                          style={{
                            border: '1px solid var(--color-danger)',
                            borderRadius: '6px',
                            padding: '7px 10px',
                            color: 'var(--color-danger)',
                            backgroundColor: 'transparent',
                            cursor: decisionInFlight === null ? 'pointer' : 'not-allowed',
                          }}
                        >
                          Rejeitar
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {decisionError && (
            <div data-testid="safety-decision-error" role="alert" style={{ color: 'var(--color-danger)', fontSize: '13px' }}>
              Não foi possível registrar a decisão: {decisionError}
            </div>
          )}
          {decisionResult && (
            <div data-testid="safety-decision-result" role="status" style={{ color: 'var(--color-success)', fontSize: '13px' }}>
              Aprovação #{decisionResult.approval.id} marcada como {decisionResult.approval.status}.
            </div>
          )}
        </Card>
      </div>

      <Card title="Timeline operacional" testId="mission-control-timeline">
        {timelineItems.length === 0 && data.timeline.status === 'ready' ? (
          <ResourceState status="empty" title="Nenhum evento observado" message="A API de telemetria ainda não retornou eventos para este projeto." testId="mission-control-timeline-state" />
        ) : data.timeline.status !== 'ready' && liveEvents.length === 0 ? (
          <PanelState resource={data.timeline} blockedMessage="Selecione um projeto para consultar a timeline." testId="mission-control-timeline-state" />
        ) : (
          <ol style={{ display: 'flex', flexDirection: 'column', gap: '10px', paddingLeft: '20px' }}>
            {timelineItems.map((event, index) => (
              <li key={`${index}-${JSON.stringify(event)}`} style={{ fontSize: '13px' }}>
                <strong>{event && typeof event === 'object' && 'event_type' in event ? String(event.event_type) : 'evento recebido'}</strong>
                <span style={{ color: 'var(--text-secondary)', display: 'block', fontFamily: 'monospace', fontSize: '11px' }}>{JSON.stringify(event)}</span>
              </li>
            ))}
          </ol>
        )}
      </Card>
    </section>
  );
}

function MetricCard({ label, value, resource }: { label: string; value: number; resource: ListResource<Task> }) {
  return (
    <Card>
      <span style={{ color: 'var(--text-secondary)', fontSize: '12px', textTransform: 'uppercase' }}>{label}</span>
      {resource.status === 'ready' ? <strong style={{ fontSize: '26px' }}>{value}</strong> : <PanelState resource={resource} blockedMessage="Selecione um projeto para consultar tarefas." testId={`mission-control-metric-${label.toLowerCase().replaceAll(' ', '-')}-state`} />}
    </Card>
  );
}
