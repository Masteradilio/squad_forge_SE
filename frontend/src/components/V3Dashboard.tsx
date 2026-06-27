import { useEffect, useState } from 'react';
import { Card } from './Card';
import { Table, type Column } from './Table';
import { Badge } from './Badge';
import { EmptyState } from './EmptyState';

interface V3DashboardProps {
  projectId: number;
}

interface SquadCompositionItem {
  role: string;
  seniority_class: string;
  responsibility: string;
  model_profile_id: string;
  provider: string;
}

interface PricingSnapshotItem {
  id: number;
  pricing_source_id: number;
  model_name: string;
  input_price_per_million: number;
  output_price_per_million: number;
  cached_input_price_per_million: number;
}

interface CostReportData {
  benchmarks: {
    actual_paid_usd: number;
    actual_calls: number;
    local_calls_avoided: number;
    openai_hypothetical_usd: number;
    anthropic_hypothetical_usd: number;
    google_hypothetical_usd: number;
    openai_savings_usd: number;
    anthropic_savings_usd: number;
    google_savings_usd: number;
  };
  by_role: Record<string, number>;
  by_task: Record<string, number>;
  snapshots: PricingSnapshotItem[];
}

export function V3Dashboard({ projectId }: V3DashboardProps) {
  const [squad, setSquad] = useState<SquadCompositionItem[]>([]);
  const [costs, setCosts] = useState<CostReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);

      const squadRes = await fetch(`/api/projects/${projectId}/squad-composition`);
      if (!squadRes.ok) throw new Error('Failed to load squad composition');
      const squadData = await squadRes.json();
      setSquad(squadData);

      const costRes = await fetch(`/api/projects/${projectId}/costs/report`);
      if (!costRes.ok) throw new Error('Failed to load cost report');
      const costData = await costRes.json();
      setCosts(costData);
    } catch (err: any) {
      setError(err.message || 'Error loading dashboard data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [projectId]);

  if (loading) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
        Loading V3 Dashboard metrics...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '24px' }}>
        <Card title="Error">
          <div style={{ color: 'var(--color-danger)' }}>{error}</div>
          <button
            onClick={loadData}
            style={{
              marginTop: '12px',
              padding: '8px 16px',
              borderRadius: '6px',
              backgroundColor: 'var(--color-primary)',
              color: '#fff',
              border: 'none',
              cursor: 'pointer'
            }}
          >
            Retry
          </button>
        </Card>
      </div>
    );
  }

  const squadColumns: Column<SquadCompositionItem>[] = [
    {
      header: 'Squad Role',
      accessor: (row) => <strong>{row.role}</strong>
    },
    {
      header: 'Seniority Class',
      accessor: (row) => {
        let variant: 'success' | 'warning' | 'danger' | 'info' | 'primary' | 'muted' | 'blocked' = 'muted';
        if (row.seniority_class.includes('chief')) variant = 'danger';
        else if (row.seniority_class.includes('local')) variant = 'success';
        return <Badge label={row.seniority_class} variant={variant} />;
      }
    },
    {
      header: 'Responsibility',
      accessor: (row) => <span>{row.responsibility}</span>
    },
    {
      header: 'Mapped Model / Tier',
      accessor: (row) => <code style={{ color: 'var(--color-primary)' }}>{row.model_profile_id}</code>
    },
    {
      header: 'Provider',
      accessor: (row) => <span style={{ textTransform: 'uppercase', fontSize: '11px', fontWeight: 600 }}>{row.provider}</span>
    },
  ];

  const snapshotColumns: Column<PricingSnapshotItem>[] = [
    {
      header: 'Snapshot ID',
      accessor: (row) => <code style={{ color: 'var(--color-primary)' }}>#{row.id}</code>
    },
    {
      header: 'Model Name',
      accessor: (row) => <span>{row.model_name}</span>
    },
    {
      header: 'Input / 1M tokens',
      accessor: (row) => <span>${row.input_price_per_million.toFixed(2)}</span>
    },
    {
      header: 'Output / 1M tokens',
      accessor: (row) => <span>${row.output_price_per_million.toFixed(2)}</span>
    },
  ];

  const benchmarks = costs?.benchmarks;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>

      {/* 1. Squad Section */}
      <Card title="V3 Autonomous Engineering Squad">
        <div style={{ marginBottom: '12px', fontSize: '14px', color: 'var(--text-secondary)' }}>
          Active roles and seniority-based routing paths mapped for this project sprint.
        </div>
        <Table
          columns={squadColumns}
          data={squad}
          emptyMessage="No squad composition data found."
        />
      </Card>

      {/* 2. Financial Metrics Overview */}
      {benchmarks && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>

          <Card title="Actual Spend (Real-Time)">
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '16px 0' }}>
              <div style={{ fontSize: '48px', fontWeight: 700, color: 'var(--color-success)' }}>
                ${benchmarks.actual_paid_usd.toFixed(4)}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
                Paid API Calls: {benchmarks.actual_calls} | Local Calls Saved: {benchmarks.local_calls_avoided}
              </div>
            </div>
          </Card>

          <Card title="Competitor API-Only baselines">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '8px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '6px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>OpenAI API-Only:</span>
                <strong style={{ fontFamily: 'monospace' }}>${benchmarks.openai_hypothetical_usd.toFixed(4)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '6px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Anthropic API-Only:</span>
                <strong style={{ fontFamily: 'monospace' }}>${benchmarks.anthropic_hypothetical_usd.toFixed(4)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '6px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Google API-Only:</span>
                <strong style={{ fontFamily: 'monospace' }}>${benchmarks.google_hypothetical_usd.toFixed(4)}</strong>
              </div>
            </div>
          </Card>

          <Card title="Economy Net Savings">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '8px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '6px' }}>
                <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>vs OpenAI:</span>
                <strong style={{ color: 'var(--color-success)', fontFamily: 'monospace' }}>
                  +${benchmarks.openai_savings_usd.toFixed(4)} (
                  {benchmarks.openai_hypothetical_usd > 0 ? ((benchmarks.openai_savings_usd / benchmarks.openai_hypothetical_usd) * 100).toFixed(1) : '0.0'}%)
                </strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '6px' }}>
                <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>vs Anthropic:</span>
                <strong style={{ color: 'var(--color-success)', fontFamily: 'monospace' }}>
                  +${benchmarks.anthropic_savings_usd.toFixed(4)} (
                  {benchmarks.anthropic_hypothetical_usd > 0 ? ((benchmarks.anthropic_savings_usd / benchmarks.anthropic_hypothetical_usd) * 100).toFixed(1) : '0.0'}%)
                </strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '6px' }}>
                <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>vs Google:</span>
                <strong style={{ color: 'var(--color-success)', fontFamily: 'monospace' }}>
                  +${benchmarks.google_savings_usd.toFixed(4)} (
                  {benchmarks.google_hypothetical_usd > 0 ? ((benchmarks.google_savings_usd / benchmarks.google_hypothetical_usd) * 100).toFixed(1) : '0.0'}%)
                </strong>
              </div>
            </div>
          </Card>

        </div>
      )}

      {/* 3. Breakdown Cost Details */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '24px' }}>

        <Card title="Paid API Cost by Role">
          {costs && Object.keys(costs.by_role).length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {Object.entries(costs.by_role).map(([role, cost]) => (
                <div key={role} style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '6px' }}>
                  <span>{role}</span>
                  <strong style={{ fontFamily: 'monospace' }}>${cost.toFixed(4)}</strong>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="No active costs" message="No model calls have generated paid API costs for this project." />
          )}
        </Card>

        <Card title="Paid API Cost by Task">
          {costs && Object.keys(costs.by_task).length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {Object.entries(costs.by_task).map(([task, cost]) => (
                <div key={task} style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '6px' }}>
                  <span>{task}</span>
                  <strong style={{ fontFamily: 'monospace' }}>${cost.toFixed(4)}</strong>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="No task costs" message="No tasks have generated paid API costs for this project." />
          )}
        </Card>

      </div>

      {/* 4. Pricing Snapshots Registry */}
      <Card title="Active Pricing Snapshots Registry">
        <div style={{ marginBottom: '12px', fontSize: '14px', color: 'var(--text-secondary)' }}>
          Immutable pricing snapshots and IDs references used to estimate competitor triads benchmarks.
        </div>
        <Table
          columns={snapshotColumns}
          data={costs?.snapshots || []}
          emptyMessage="No pricing snapshots seeded in database."
        />
      </Card>

    </div>
  );
}
