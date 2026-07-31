import { useState } from 'react';
import { Card } from './Card';
import { Button } from './Button';
import { Badge } from './Badge';

interface ComplianceTestsViewProps {
  onNavigateToTab: (tab: string) => void;
}

export function ComplianceTestsView({ onNavigateToTab }: ComplianceTestsViewProps) {
  const [secStatus, setSecStatus] = useState<'scanning' | 'clean' | 'flaws'>('clean');
  const [funcStatus, setFuncStatus] = useState<'testing' | 'clean' | 'flaws'>('clean');
  const [activeReportTab, setActiveReportTab] = useState<'security' | 'functional' | 'dossier'>('security');

  const secReportMock = `# 🛡️ Relatório de Conformidade de Segurança

**Data da Auditoria**: ${new Date().toLocaleDateString()}
**Branch Auditada**: main
**Status Geral de Segurança**: CONFORME 🟢

## 🔍 Resumo Executivo das Vulnerabilidades
- **Vulnerabilidades Críticas**: 0
- **Vulnerabilidades de Alta Gravidade**: 0
- **Vulnerabilidades de Média Gravidade**: 0
- **Segredos/Chaves Hardcoded Encontradas**: 0

## 🛡️ Atestado de Conformidade
- [x] Código fonte isento de credenciais/segredos hardcoded
- [x] Endpoints e entrada de dados sanitizados
- [x] Manutenção de permissões e privilégios mínimos
- [x] Ausência de CVEs conhecidas nas dependências
`;

  const funcReportMock = `# 🧪 Relatório de Conformidade Funcional E2E

**Data do Teste**: ${new Date().toLocaleDateString()}
**Produto Testado**: LocalForge Project
**Status Geral de Conformidade**: CONFORME 🟢

## 📊 Resumo de Execução E2E
- **Total de Requisitos do PRD**: 18
- **Requisitos Aprovados (PASSED)**: 18
- **Requisitos Reprovados (FAILED)**: 0
- **Taxa de Conformidade Funcional**: 100%

## 🏆 Matriz de Rastreabilidade PRD vs. Teste
| Requisito PRD | Funcionalidade | Ferramenta Utilizada | Status |
| --- | --- | --- | :---: |
| REQ-01 | Layout & Chassis Visual | Playwright Browser | PASSED 🟢 |
| REQ-02 | RPN Stack Operations | Subprocess CLI | PASSED 🟢 |
| REQ-03 | Financial TVM Solver | HTTP API Client | PASSED 🟢 |
`;

  const dossierMock = `# 🏆 Dossiê Executivo de Liberação

**Data da Liberação**: ${new Date().toLocaleDateString()}
**Status de Conformidade Final**: CONFORME 🟢
**Total de Ciclos de Remediação**: 1
**Checksum SHA-256 do Produto**: \`fe35c8a01b9d45ddba67841b3d89602200612bbb69f643080f97cbeb0728b3d7\`

---

## 📦 Artefato Final do Produto
- **Caminho da Compilação**: \`frontend/public/hp12c.html\`
- **Assinatura de Segurança**: Aprovada 🛡️
- **Assinatura Funcional E2E**: Aprovada 🧪

## 📊 Curva de Convergência dos Ciclos de Qualidade
| Ciclo | Status Segurança | Falhas Segurança | Status Funcional | Não Conformidades E2E |
| :---: | :---: | :---: | :---: | :---: |
| cycle_1 | CONFORME | 0 | CONFORME | 0 |
`;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 800, margin: 0 }}>🧪 Testes de Conformidade Pós-Merge</h1>
          <p style={{ color: 'var(--text-secondary)', margin: '4px 0 0 0', fontSize: '14px' }}>
            Etapas 5 e 6: Varredura de Segurança (Security Auditor) e Testes E2E (Release Tester).
          </p>
        </div>
        <Button variant="secondary" onClick={() => onNavigateToTab('chat')}>
          💬 Voltar ao Chat & Dossiê →
        </Button>
      </div>

      {/* Main Dual-Pane Section */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        {/* Left Column: Agents Progress */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Top Panel: Security Auditor */}
          <Card style={{ padding: '20px', borderLeft: '4px solid #10b981' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <h3 style={{ margin: 0, fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                🛡️ Agente de Segurança (Security Auditor)
              </h3>
              <Badge variant="success">CONFORME 🟢</Badge>
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
              Varredura de vulnerabilidades SAST, segredos hardcoded e dependências inseguras na branch `main`.
            </p>
            <div style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '6px', backgroundColor: 'var(--bg-input)', padding: '12px', borderRadius: '6px' }}>
              <div>✔ Varredura SAST de código fonte concluída (0 alertas)</div>
              <div>✔ Detecção de chaves/segredos hardcoded: Limpo</div>
              <div>✔ Análise de dependências CVE: Nenhuma vulnerabilidade encontrada</div>
            </div>
          </Card>

          {/* Bottom Panel: E2E Release Tester */}
          <Card style={{ padding: '20px', borderLeft: '4px solid #3b82f6' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <h3 style={{ margin: 0, fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                🧪 Agente Tester (E2E Release Tester)
              </h3>
              <Badge variant="success">100% CONFORME 🟢</Badge>
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
              Validação comportamental do produto compilado contra os requisitos do PRD.md original.
            </p>
            <div style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '6px', backgroundColor: 'var(--bg-input)', padding: '12px', borderRadius: '6px' }}>
              <div>✔ Automação de Navegador (Playwright Driver): 18/18 cenários aprovados</div>
              <div>✔ Testes de Cliente HTTP & API Server: 100% de sucesso</div>
              <div>✔ Efeitos colaterais em banco de dados SQLite: Verificados</div>
            </div>
          </Card>
        </div>

        {/* Right Column: Interactive Report Panel */}
        <Card style={{ padding: '20px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
            <Button
              variant={activeReportTab === 'security' ? 'primary' : 'secondary'}
              onClick={() => setActiveReportTab('security')}
            >
              🛡️ Relatório de Segurança
            </Button>
            <Button
              variant={activeReportTab === 'functional' ? 'primary' : 'secondary'}
              onClick={() => setActiveReportTab('functional')}
            >
              🧪 Relatório Funcional
            </Button>
            <Button
              variant={activeReportTab === 'dossier' ? 'primary' : 'secondary'}
              onClick={() => setActiveReportTab('dossier')}
            >
              🏆 Dossiê Executivo
            </Button>
          </div>

          <div style={{ flex: 1, backgroundColor: 'var(--bg-input)', padding: '16px', borderRadius: '8px', overflowY: 'auto', fontFamily: 'monospace', fontSize: '13px', whiteSpace: 'pre-wrap', lineHeight: '1.6' }}>
            {activeReportTab === 'security' && secReportMock}
            {activeReportTab === 'functional' && funcReportMock}
            {activeReportTab === 'dossier' && dossierMock}
          </div>
        </Card>
      </div>
    </div>
  );
}
