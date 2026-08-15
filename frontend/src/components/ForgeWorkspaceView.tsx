import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
} from 'react';
import {
  apiClient,
  type ChatMessageItem,
  type Project,
  type Task,
} from '../api/client';
import type { LifecycleEventPayload } from '../api/events';
import { Button } from './Button';
import type { TraceSpanItem } from './TracingTimelineView';

type PipelineStage = 'backlog' | 'execution' | 'pr' | 'security' | 'tester';

interface PipelineColumn {
  id: PipelineStage;
  title: string;
  description: string;
  accent: string;
}

// eslint-disable-next-line react-refresh/only-export-components
export const PIPELINE_COLUMNS: PipelineColumn[] = [
  {
    id: 'backlog',
    title: 'Backlog',
    description: 'Tarefas criadas pelo Scrum Master',
    accent: '#60a5fa',
  },
  {
    id: 'execution',
    title: 'Execucao e correcao',
    description: 'Implementacao, revisao e retornos',
    accent: '#f59e0b',
  },
  {
    id: 'pr',
    title: 'PR_READY / Merge',
    description: 'Aguardando merge ou devolucao',
    accent: '#a78bfa',
  },
  {
    id: 'security',
    title: 'Security Auditor',
    description: 'Auditoria pos-merge e traces',
    accent: '#f87171',
  },
  {
    id: 'tester',
    title: 'Tester final',
    description: 'Aceitacao E2E do produto entregue',
    accent: '#34d399',
  },
];

interface WorkspaceMessage {
  id: number;
  sender: 'PO' | 'Scrum Master' | 'System';
  text: string;
  attachments?: string[];
  createdAt?: string;
}

interface ForgeWorkspaceViewProps {
  activeProject: Project | null;
  tasks: Task[];
  events: LifecycleEventPayload[];
  telemetrySpans: TraceSpanItem[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onSelectProject: (projectId: number) => void;
}

function eventText(event: LifecycleEventPayload): string {
  const payload = event.payload || {};
  return [
    event.event_type,
    ...Object.entries(payload).map(([key, value]) => key + ' ' + String(value)),
  ]
    .join(' ')
    .toLowerCase();
}

function isSecurityEvidence(text: string): boolean {
  return text.includes('security') || text.includes('safety') || text.includes('auditor');
}

function isTesterEvidence(text: string): boolean {
  return text.includes('tester') || text.includes('e2e') || text.includes('acceptance') || text.includes('test.finished');
}

function isPostMergeEvent(event: LifecycleEventPayload): boolean {
  const text = eventText(event);
  return isSecurityEvidence(text) || isTesterEvidence(text);
}

function relatedTaskEvents(task: Task, events: LifecycleEventPayload[]): LifecycleEventPayload[] {
  return events
    .filter((event) => {
      const payload = event.payload || {};
      const payloadTaskId = payload.task_id ?? payload.taskId;
      return (
        String(payloadTaskId ?? '') === String(task.id) ||
        eventText(event).includes(task.key.toLowerCase())
      );
    })
    .sort((left, right) => {
      const leftTime = left.created_at ? Date.parse(left.created_at) : 0;
      const rightTime = right.created_at ? Date.parse(right.created_at) : 0;
      return rightTime - leftTime;
    });
}

// eslint-disable-next-line react-refresh/only-export-components
export function stageForTask(task: Task, events: LifecycleEventPayload[]): PipelineStage {
  const status = task.status.toUpperCase();
  const taskEvents = relatedTaskEvents(task, events);
  const latestPostMergeEvent = taskEvents.find(isPostMergeEvent);

  if (status === 'BACKLOG' || status === 'PLANNING') return 'backlog';
  if (status === 'PR_READY') return 'pr';
  if (status === 'DONE') {
    if (latestPostMergeEvent && eventText(latestPostMergeEvent).includes('security')) {
      return 'security';
    }
    return 'tester';
  }
  return 'execution';
}

function formatTime(value?: string): string {
  if (!value) return '--:--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--:--';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function describeEvent(event: LifecycleEventPayload): string {
  const payload = event.payload || {};
  const candidate = payload.message ?? payload.summary ?? payload.reason ?? payload.status;
  return candidate ? String(candidate) : event.event_type;
}

function spanText(span: TraceSpanItem): string {
  return (span.role_name + ' ' + span.action_name).toLowerCase();
}

function readFile(file: File, asDataUrl = false): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error('Falha ao ler o arquivo.'));
    reader.onload = () => resolve(String(reader.result || ''));
    if (asDataUrl) reader.readAsDataURL(file);
    else reader.readAsText(file);
  });
}

function mapChatMessage(message: ChatMessageItem): WorkspaceMessage {
  return {
    id: message.id,
    sender: message.sender,
    text: message.text,
    attachments: message.attachments,
    createdAt: message.created_at,
  };
}

export function ForgeWorkspaceView({
  activeProject,
  tasks,
  events,
  telemetrySpans,
  loading,
  error,
  onRefresh,
  onSelectProject,
}: ForgeWorkspaceViewProps) {
  const [messages, setMessages] = useState<WorkspaceMessage[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [message, setMessage] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [actionTaskId, setActionTaskId] = useState<number | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSession = useCallback(async () => {
    try {
      const sessions = await apiClient.fetchChatSessions();
      const projectSession = activeProject
        ? sessions.find((session) => session.project_id === activeProject.id)
        : undefined;
      const session = projectSession || sessions[0] || await apiClient.createChatSession(
        activeProject ? activeProject.name + ' workspace' : 'ForgeOS workspace',
      );
      const details = await apiClient.fetchChatSessionDetails(session.id);
      setSessionId(session.id);
      setMessages((details.messages || []).map(mapChatMessage));
      setWorkspaceError(null);
    } catch (loadError) {
      console.error('Failed to load the unified workspace session:', loadError);
      setWorkspaceError(loadError instanceof Error ? loadError.message : String(loadError));
    }
  }, [activeProject]);

  useEffect(() => {
    // Session state is synchronized with the backend after the active project changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadSession();
  }, [loadSession]);

  const tasksByStage = useMemo(() => {
    const grouped: Record<PipelineStage, Task[]> = {
      backlog: [],
      execution: [],
      pr: [],
      security: [],
      tester: [],
    };
    tasks.forEach((task) => grouped[stageForTask(task, events)].push(task));
    return grouped;
  }, [events, tasks]);

  const postMergeEvents = useMemo(
    () => events.filter(isPostMergeEvent).slice(0, 40),
    [events],
  );

  const postMergeSpans = useMemo(
    () => telemetrySpans.filter((span) => {
      const text = spanText(span);
      return (
        text.includes('security') ||
        text.includes('safety') ||
        text.includes('auditor') ||
        text.includes('tester') ||
        text.includes('e2e')
      );
    }).slice(0, 40),
    [telemetrySpans],
  );

  const securityEvents = useMemo(
    () => postMergeEvents.filter((event) => isSecurityEvidence(eventText(event))),
    [postMergeEvents],
  );

  const testerEvents = useMemo(
    () => postMergeEvents.filter((event) => !isSecurityEvidence(eventText(event))),
    [postMergeEvents],
  );

  const securitySpans = useMemo(
    () => postMergeSpans.filter((span) => isSecurityEvidence(spanText(span))),
    [postMergeSpans],
  );

  const testerSpans = useMemo(
    () => postMergeSpans.filter((span) => !isSecurityEvidence(spanText(span))),
    [postMergeSpans],
  );

  const renderTraceRows = (
    traceEvents: LifecycleEventPayload[],
    traceSpans: TraceSpanItem[],
  ) => (
    <div className="trace-grid">
      {traceEvents.map((event, index) => (
        <div className="trace-row" key={String(event.id ?? index) + '-' + event.event_type}>
          <span className="trace-kind">EVENT</span>
          <strong>{event.event_type}</strong>
          <span>{describeEvent(event)}</span>
          <time>{formatTime(event.created_at)}</time>
        </div>
      ))}
      {traceSpans.map((span) => (
        <div className="trace-row" key={span.span_id}>
          <span className="trace-kind trace-kind-span">SPAN</span>
          <strong>{span.role_name}</strong>
          <span>{span.action_name}</span>
          <time>{span.duration_ms ? String(span.duration_ms) + ' ms' : 'running'}</time>
        </div>
      ))}
      {traceEvents.length === 0 && traceSpans.length === 0 && (
        <div className="trace-group-empty">Aguardando evidencias desta etapa</div>
      )}
    </div>
  );

  const handleStartSquad = async () => {
    if (!activeProject) {
      setWorkspaceError('Selecione um projeto antes de iniciar a Squad.');
      return;
    }
    setIsStarting(true);
    setWorkspaceError(null);
    try {
      await apiClient.startSquad(activeProject.id);
      onRefresh();
    } catch (startError) {
      setWorkspaceError(startError instanceof Error ? startError.message : String(startError));
    } finally {
      setIsStarting(false);
    }
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setSelectedFiles(Array.from(event.target.files || []));
  };

  const handleSend = async () => {
    const trimmedMessage = message.trim();
    if ((!trimmedMessage && selectedFiles.length === 0) || isSending) return;

    const attachmentNames = selectedFiles.map((file) => file.name);
    const localMessage: WorkspaceMessage = {
      id: Date.now(),
      sender: 'PO',
      text: trimmedMessage || 'Analise os documentos anexados e transforme-os em backlog.',
      attachments: attachmentNames,
    };
    setMessages((current) => [...current, localMessage]);
    setMessage('');
    setIsSending(true);
    setWorkspaceError(null);

    try {
      const prdFile = selectedFiles.find((file) => /\.(md|markdown|txt)$/i.test(file.name));
      const imageFile = selectedFiles.find((file) => /\.(png|jpe?g|webp|svg)$/i.test(file.name));
      let prdPath: string | undefined;

      if (prdFile && activeProject) {
        const prdContent = await readFile(prdFile);
        const imageData = imageFile ? await readFile(imageFile, true) : undefined;
        const intake = await apiClient.intakeProjectInputs({
          name: activeProject.name,
          root_path: activeProject.root_path,
          project_id: activeProject.id,
          prd_content: prdContent,
          design_image_name: imageFile?.name,
          design_image_base64: imageData,
        });
        prdPath = intake.prd_path;
        onSelectProject(intake.project.id);
      }

      const response = await apiClient.poScrumMasterChat(
        localMessage.text,
        attachmentNames,
        activeProject?.id,
        sessionId ?? undefined,
        prdPath,
      );
      if (response.project) onSelectProject(response.project.id);
      await loadSession();
      onRefresh();
    } catch (sendError) {
      setWorkspaceError(sendError instanceof Error ? sendError.message : String(sendError));
    } finally {
      setSelectedFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = '';
      setIsSending(false);
    }
  };

  const handlePRAction = async (task: Task, action: 'merge' | 'return') => {
    setActionTaskId(task.id);
    setWorkspaceError(null);
    try {
      if (action === 'merge') {
        await apiClient.approvePR(task.id);
      } else {
        await apiClient.rejectPR(
          task.id,
          'Produto devolvido pela auditoria visual/funcional para correcao antes da proxima etapa.',
        );
      }
      onRefresh();
    } catch (actionError) {
      setWorkspaceError(actionError instanceof Error ? actionError.message : String(actionError));
    } finally {
      setActionTaskId(null);
    }
  };

  return (
    <section className="forge-workspace" aria-label="ForgeOS unified workspace">
      <header className="workspace-header">
        <div>
          <div className="eyebrow">FORGEOS WORKSPACE</div>
          <h1>Do documento ao software entregue</h1>
          <p>
            O Scrum Master recebe o contexto abaixo e a Squad avanca pelo pipeline com
            evidencias de seguranca e aceitacao E2E.
          </p>
        </div>
        <div className="workspace-header-actions">
          <span className="project-pill">
            {activeProject ? activeProject.name : 'Nenhum projeto selecionado'}
          </span>
          <Button variant="primary" onClick={() => void handleStartSquad()} loading={isStarting}>
            Iniciar Squad
          </Button>
        </div>
      </header>

      <div className="pipeline-summary" aria-label="Pipeline summary">
        <span className="live-dot" />
        <strong>{tasks.length}</strong> tarefas acompanhadas ao vivo
        <span className="summary-separator">|</span>
        <strong>{postMergeEvents.length + postMergeSpans.length}</strong> evidencias de Security Auditor e Tester
        {loading && <span className="summary-loading">Sincronizando...</span>}
      </div>

      {error && <div className="workspace-inline-error">{error}</div>}
      {workspaceError && <div className="workspace-inline-error">{workspaceError}</div>}

      <div className="forge-kanban" data-testid="forge-pipeline-board">
        {PIPELINE_COLUMNS.map((column) => (
          <section
            key={column.id}
            className="forge-lane"
            data-testid={'forge-lane-' + column.id}
            style={{ '--lane-accent': column.accent } as CSSProperties}
          >
            <div className="lane-heading">
              <div>
                <h2>{column.title}</h2>
                <p>{column.description}</p>
              </div>
              <span className="lane-count">{tasksByStage[column.id].length}</span>
            </div>
            <div className="lane-body">
              {tasksByStage[column.id].map((task) => (
                <article className="pipeline-card" key={task.id}>
                  <div className="pipeline-card-meta">
                    <span>{task.key}</span>
                    <span className="task-status">{task.status}</span>
                  </div>
                  <h3>{task.title}</h3>
                  {task.acceptance_criteria && task.acceptance_criteria.length > 0 && (
                    <span className="task-criteria">
                      {task.acceptance_criteria.length} criterios de aceite
                    </span>
                  )}
                  {column.id === 'pr' && (
                    <div className="pipeline-card-actions">
                      <Button
                        variant="success"
                        onClick={() => void handlePRAction(task, 'merge')}
                        loading={actionTaskId === task.id}
                      >
                        Merge na main
                      </Button>
                      <Button
                        variant="warning"
                        onClick={() => void handlePRAction(task, 'return')}
                        disabled={actionTaskId === task.id}
                      >
                        Devolver
                      </Button>
                    </div>
                  )}
                  {(column.id === 'security' || column.id === 'tester') && (
                    <div className="pipeline-card-actions">
                      <Button
                        variant="warning"
                        onClick={() => void handlePRAction(task, 'return')}
                        loading={actionTaskId === task.id}
                      >
                        Retornar para correcao
                      </Button>
                    </div>
                  )}
                </article>
              ))}
              {tasksByStage[column.id].length === 0 && (
                <div className="lane-empty">Aguardando movimentacao</div>
              )}
            </div>
          </section>
        ))}
      </div>

      <section className="post-merge-traces" aria-label="Post merge traces">
        <div className="section-heading">
          <div>
            <div className="eyebrow">POST-MERGE QUALITY GATES</div>
            <h2>Security Auditor e Tester final</h2>
          </div>
          <span className="trace-count">{postMergeEvents.length + postMergeSpans.length} traces</span>
        </div>
        {postMergeEvents.length === 0 && postMergeSpans.length === 0 ? (
          <p className="trace-empty">
            Os logs e traces aparecerao aqui depois que as PR_READY forem mergeadas.
          </p>
        ) : (
          <div className="trace-groups">
            <section className="trace-group" aria-label="Security Auditor traces">
              <div className="trace-group-heading">
                <span className="trace-agent security-agent">1. Security Auditor</span>
                <span>{securityEvents.length + securitySpans.length} evidencias</span>
              </div>
              {renderTraceRows(securityEvents, securitySpans)}
            </section>
            <section className="trace-group" aria-label="Tester final traces">
              <div className="trace-group-heading">
                <span className="trace-agent tester-agent">2. Tester final</span>
                <span>{testerEvents.length + testerSpans.length} evidencias</span>
              </div>
              {renderTraceRows(testerEvents, testerSpans)}
            </section>
          </div>
        )}
      </section>

      <section className="workspace-chat" aria-label="Scrum Master chat">
        <div className="section-heading">
          <div>
            <div className="eyebrow">CONVERSA DE ENTRADA</div>
            <h2>Chat com o Scrum Master</h2>
          </div>
          {sessionId && <span className="session-label">sessao #{sessionId}</span>}
        </div>
        <div className="workspace-messages" aria-live="polite">
          {messages.length === 0 && (
            <p className="chat-empty">
              Envie um PRD, uma imagem de referencia ou uma instrucao para iniciar o backlog.
            </p>
          )}
          {messages.map((item) => (
            <article
              className={'workspace-message ' + (item.sender === 'PO' ? 'from-po' : 'from-scrum')}
              key={item.id}
            >
              <div className="message-author">{item.sender}</div>
              <p>{item.text}</p>
              {item.attachments && item.attachments.length > 0 && (
                <small>{item.attachments.join(', ')}</small>
              )}
            </article>
          ))}
          {isSending && <p className="chat-processing">Scrum Master esta analisando o contexto...</p>}
        </div>
        <div className="workspace-composer">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".md,.markdown,.txt,.png,.jpg,.jpeg,.webp,.svg"
            onChange={handleFileChange}
            hidden
          />
          <Button variant="secondary" onClick={() => fileInputRef.current?.click()}>
            Anexar documentos
          </Button>
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void handleSend();
              }
            }}
            placeholder="Descreva o produto ou a proxima instrucao..."
            rows={2}
          />
          <Button
            variant="primary"
            onClick={() => void handleSend()}
            disabled={isSending || (!message.trim() && selectedFiles.length === 0)}
          >
            Enviar
          </Button>
        </div>
        {selectedFiles.length > 0 && (
          <div className="selected-files">
            Arquivos: {selectedFiles.map((file) => file.name).join(', ')}
          </div>
        )}
      </section>
    </section>
  );
}
