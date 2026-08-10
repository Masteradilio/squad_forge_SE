import type { LifecycleEventPayload } from '../api/events';
import { Timeline, type TimelineItem } from './Timeline';

export function OperationsStream({ events }: { events: LifecycleEventPayload[] }) {
  const items: TimelineItem[] = events.map((event) => {
    let type: TimelineItem['type'] = 'info';
    if (event.event_type.includes('succeeded') || event.event_type.includes('allowed')) {
      type = 'success';
    } else if (event.event_type.includes('failed') || event.event_type.includes('blocked')) {
      type = 'danger';
    } else if (event.event_type.includes('started')) {
      type = 'primary';
    }
    return {
      title: event.event_type,
      subtitle: String(event.payload.action || event.payload.status || ''),
      content: <pre style={{ fontSize: '11px' }}>{JSON.stringify(event.payload, null, 2)}</pre>,
      type,
    };
  });

  return (
    <aside className="operations-stream" data-testid="operations-stream" style={{
      width: '320px',
      backgroundColor: 'var(--bg-sidebar)',
      borderLeft: '1px solid var(--border-color)',
      padding: '24px',
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column',
      gap: '16px',
    }}>
      <h3 style={{ fontSize: '16px', fontWeight: 600 }}>Real-time Operations Stream</h3>
      <Timeline items={items} />
    </aside>
  );
}
