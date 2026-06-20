import { useEffect, useState, useRef } from 'react';

export interface LifecycleEventPayload {
  project_id: number;
  run_id?: number;
  event_type: string;
  payload: Record<string, any>;
  id?: number;
  created_at?: string;
}

const EVENT_TYPES = [
  'run.started',
  'task.status_changed',
  'agent.action_requested',
  'safety.action_allowed',
  'safety.action_blocked',
  'test.finished',
  'repair.started',
  'repair.succeeded',
  'repair.failed',
  'pr.created',
  'artifact.created',
  'system.event',
];

export function useProjectEvents(
  projectId: number,
  onEvent: (event: LifecycleEventPayload) => void
) {
  const [connected, setConnected] = useState(false);
  const lastEventIdRef = useRef<number>(0);

  useEffect(() => {
    if (!projectId) return;

    let active = true;
    let eventSource: EventSource | null = null;

    const connect = () => {
      if (!active) return;

      const url = `/api/projects/${projectId}/events?last_event_id=${lastEventIdRef.current}`;
      eventSource = new EventSource(url);

      eventSource.onopen = () => {
        if (active) setConnected(true);
      };

      eventSource.onerror = () => {
        if (active) {
          setConnected(false);
          eventSource?.close();
          // Reconnect with delay
          setTimeout(connect, 3000);
        }
      };

      EVENT_TYPES.forEach((type) => {
        eventSource?.addEventListener(type, (e: MessageEvent) => {
          if (!active) return;
          try {
            const data = JSON.parse(e.data);
            const eventId = e.lastEventId ? parseInt(e.lastEventId, 10) : 0;
            if (eventId > lastEventIdRef.current) {
              lastEventIdRef.current = eventId;
            }
            onEvent({
              project_id: projectId,
              event_type: type,
              payload: data.payload || data,
              id: eventId || undefined,
            });
          } catch (err) {
            console.error('Failed to parse SSE payload', err);
          }
        });
      });
    };

    connect();

    return () => {
      active = false;
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [projectId, onEvent]);

  return connected;
}
