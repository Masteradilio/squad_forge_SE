import { useState } from 'react';
import { Badge } from './Badge';
import { Button } from './Button';
import { Card } from './Card';
import { ResourceState } from './ResourceState';

interface ComplianceTestsViewProps {
  projectId?: number;
  onNavigateToTab: (tab: string) => void;
}

type ReportTab = 'security' | 'functional' | 'dossier';

const REPORT_LABELS: Record<ReportTab, string> = {
  security: 'Relatório de Segurança',
  functional: 'Relatório Funcional',
  dossier: 'Dossiê Executivo',
};

export function ComplianceTestsView({ projectId, onNavigateToTab }: ComplianceTestsViewProps) {
  const [activeReportTab, setActiveReportTab] = useState<ReportTab>('security');
  const hasProject = typeof projectId === 'number';
  const reportState = hasProject ? 'empty' : 'blocked';
  const reportMessage = hasProject
    ? 'Execute o benchmark de cobertura completa para disponibilizar este relatório.'
    : 'Selecione um projeto para consultar os artefatos de conformidade.';

  return (
    <div data-testid="compliance-tests" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 800, margin: 0 }}>Testes de Conformidade</h1>
          <p style={{ color: 'var(--text-secondary)', margin: '4px 0 0', fontSize: '14px' }}>
            Relatórios exibidos somente quando produzidos por uma execução real do benchmark.
          </p>
        </div>
        <Button variant="secondary" onClick={() => onNavigateToTab('chat')}>
          Voltar ao Chat →
        </Button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px' }}>
        <CompliancePanel title="Security Auditor" description="SAST, dependências, secrets e políticas de segurança." />
        <CompliancePanel title="E2E Release Tester" description="Browser, API, CLI e efeitos persistidos do produto compilado." />
      </div>

      <Card style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {(Object.keys(REPORT_LABELS) as ReportTab[]).map((tab) => (
            <Button
              key={tab}
              variant={activeReportTab === tab ? 'primary' : 'secondary'}
              onClick={() => setActiveReportTab(tab)}
            >
              {REPORT_LABELS[tab]}
            </Button>
          ))}
        </div>
        <div data-testid={`compliance-report-${activeReportTab}`}>
          <ResourceState
            status={reportState}
            title={hasProject ? 'Relatório ainda não disponível' : 'Projeto não selecionado'}
            message={`${REPORT_LABELS[activeReportTab]}: ${reportMessage}`}
            testId={`compliance-report-state-${activeReportTab}`}
          />
        </div>
      </Card>
    </div>
  );
}

function CompliancePanel({ title, description }: { title: string; description: string }) {
  return (
    <Card style={{ padding: '20px', borderLeft: '4px solid var(--color-info)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px' }}>
        <h3 style={{ margin: 0, fontSize: '16px' }}>{title}</h3>
        <Badge variant="info">Aguardando execução</Badge>
      </div>
      <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: 0 }}>{description}</p>
    </Card>
  );
}
