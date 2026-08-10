import { useEffect, useState } from 'react';
import { apiClient, type Automation, type EngineeringSession, type ReferenceHit, type ReferenceSource } from '../api/client';
import { Alert } from './Alert';
import { Badge } from './Badge';
import { Button } from './Button';
import { Card } from './Card';

interface ForgeContinuityViewProps {
  projectId?: number;
}

export function ForgeContinuityView({ projectId }: ForgeContinuityViewProps) {
  const [sessions, setSessions] = useState<EngineeringSession[]>([]);
  const [sources, setSources] = useState<ReferenceSource[]>([]);
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [hits, setHits] = useState<ReferenceHit[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!projectId) return undefined;
    setLoading(true);
    Promise.all([
      apiClient.fetchEngineeringSessions(projectId),
      apiClient.fetchReferences(projectId),
      apiClient.fetchAutomations(projectId),
    ]).then(([nextSessions, nextSources, nextAutomations]) => {
      if (cancelled) return;
      setSessions(nextSessions);
      setSources(nextSources);
      setAutomations(nextAutomations);
      setError(null);
    }).catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [projectId]);

  const runSearch = async () => {
    if (!projectId || !query.trim()) return;
    try {
      setHits(await apiClient.searchReferences(projectId, query.trim()));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  if (!projectId) return <Card><p style={{ color: 'var(--text-muted)' }}>Selecione um projeto para abrir a continuidade de engenharia.</p></Card>;

  return (
    <section data-testid="forge-continuity-view" style={{ display: 'grid', gap: '20px' }}>
      <div>
        <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '12px', letterSpacing: '0.08em', textTransform: 'uppercase' }}>DeepCode-inspired continuity</p>
        <h2 style={{ margin: '6px 0 0' }}>Engenharia com memória, evidência e direção</h2>
      </div>
      {error && <Alert type="error">{error}</Alert>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '12px' }}>
        <Metric label="Sessions" value={sessions.length} detail={loading ? 'Sincronizando…' : 'duráveis'} />
        <Metric label="References" value={sources.length} detail="hash + quarantine" />
        <Metric label="Automations" value={automations.length} detail="same runtime" />
      </div>
      <Card>
        <h3 style={{ marginTop: 0 }}>CodeRAG lexical search</h3>
        <div style={{ display: 'flex', gap: '8px' }}>
          <input aria-label="Reference search" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void runSearch(); }} placeholder="ex.: billing invoice acceptance" style={{ flex: 1, padding: '10px', background: 'var(--bg-input)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: '6px' }} />
          <Button onClick={() => void runSearch()}>Buscar evidência</Button>
        </div>
        <div style={{ display: 'grid', gap: '8px', marginTop: '12px' }}>
          {hits.map((hit) => <div key={hit.chunk_id} style={{ padding: '10px', border: '1px solid var(--border-color)', borderRadius: '6px' }}><Badge>{hit.citation}</Badge><p style={{ marginBottom: 0 }}>{hit.text}</p></div>)}
          {!hits.length && <p style={{ color: 'var(--text-muted)' }}>As citações selecionadas aparecerão aqui.</p>}
        </div>
      </Card>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '12px' }}>
        <Card><h3 style={{ marginTop: 0 }}>Goals / Sessions</h3>{sessions.length ? sessions.map((session) => <div key={session.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}><span>{session.title}</span><Badge>{session.status}</Badge></div>) : <p style={{ color: 'var(--text-muted)' }}>Nenhuma session registrada.</p>}</Card>
        <Card><h3 style={{ marginTop: 0 }}>Reference sources</h3>{sources.length ? sources.map((source) => <div key={source.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}><span>{source.name}</span><Badge>{source.injection_status}</Badge></div>) : <p style={{ color: 'var(--text-muted)' }}>Nenhuma fonte ingerida.</p>}</Card>
      </div>
    </section>
  );
}

function Metric({ label, value, detail }: { label: string; value: number; detail: string }) {
  return <Card><div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{label}</div><strong style={{ fontSize: '28px' }}>{value}</strong><div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{detail}</div></Card>;
}
