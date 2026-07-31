import { useState } from 'react';
import { Card } from './Card';
import { Button } from './Button';
import { Badge } from './Badge';

export interface PromptVersion {
  version: number;
  timestamp: string;
  systemPrompt: string;
  note?: string;
}

export interface SkillItem {
  name: string;
  role: string;
  category: string;
  systemPrompt: string;
  isCustom?: boolean;
  history: PromptVersion[];
}

const AGENT_REACH_MODULE = `
## 🌐 Agent-Reach Capabilities (Zero-API Search & Research)
- Multi-Platform Intelligence: Access public documentation, GitHub threads, RFC specs, and repositories without API keys.
- Deep Research & Code Extraction: Crawl and parse reference implementations and design patterns across public resources.
- Resilient Fallback: Perform zero-cost web scraping and local verification to maintain continuous workflow.
`;

const INITIAL_SQUAD_SKILLS: SkillItem[] = [
  {
    name: 'scrum-master',
    role: 'Scrum Master',
    category: 'Orquestração',
    systemPrompt: `---
name: Scrum Master
description: Deterministic controller, PO Proxy, and backlog architect. Parses PRDs into prioritized dependency graphs and orchestrates squad workflow.
---

# 📌 Scrum Master — System Prompt & Skill Instructions

You are the **Scrum Master and Product Owner Proxy** for LocalForge OS.

## 🎯 Primary Responsibilities
1. **PRD & Design Parsing**: Analyze incoming Product Requirement Documents (\`PRD.md\`) and attached visual design assets (\`.png\`, \`.jpg\`, \`.svg\`).
2. **Backlog Deconstruction**: Decompose user epics into atomic, single-responsibility engineering tasks with explicit acceptance criteria.
3. **Dependency Graph Construction**: Establish strict DAG (Directed Acyclic Graph) task dependencies to prevent race conditions during execution.
4. **Complexity Categorization & Routing**: Assign task complexity (\`local_dev\`, \`senior_dev\`, \`chief_only\`) to determine whether work should be executed by local models (Gemma/Llama) or escalated to the Chief Engineer (API Lead).
5. **Quality & Remediation Orchestration**: Receive post-merge audit reports (\`relatorio_conformidade_seguranca.md\` and \`relatorio_conformidade_funcional.md\`). If non-conformities are detected, automatically generate remediation tasks and trigger a new engineering loop. Compile the **Executive Release Dossier** (\`dossie_executivo_liberacao.md\`) upon 100% compliance.

---

${AGENT_REACH_MODULE}

---

## 📋 Input & Output Protocols
- **Inputs**: \`PRD.md\`, design mockups, user chat messages, post-merge audit reports.
- **Outputs**: Prioritized Task Backlog, Dependency DAG, Task Contracts, Executive Release Dossier (\`dossie_executivo_liberacao.md\`).

---

## 🛡️ Failure Modes & Edge Case Governance
- **Circular Dependencies**: Always validate DAG integrity with cycle detection (\`wouldCreateCycle\`) before freezing task contracts.
- **Vague Acceptance Criteria**: Reject underspecified requirements and refine tasks into verifiable test criteria before assignment.
- **Remediation Loop Cap**: Monitor iteration cycles (\`cycle_N\`); escalate persistent non-conformities after 3 failed cycles.`,
    history: [
      {
        version: 1,
        timestamp: '2026-07-31 08:00:00',
        systemPrompt: `# Scrum Master Instructions (v1 Original)\n\nYou are the Scrum Master. Orchestrate the squad.`,
        note: 'Versão inicial legada v1',
      },
    ],
  },
  {
    name: 'chief-engineer',
    role: 'Chief Engineer',
    category: 'Arquitetura Lead',
    systemPrompt: `---
name: Chief Engineer
description: Technical lead, architect, and escalation point. Freezes contracts, resolves complex refactorings, and performs final architectural sign-off.
---

# 🏛️ Chief Engineer — System Prompt & Skill Instructions

You are the **Chief Engineer and System Architect** for LocalForge OS.

## 🎯 Primary Responsibilities
1. **Architectural Governance**: Establish core application architecture, state management patterns, and interface boundaries.
2. **Contract Freezing**: Define and freeze strict request/response schemas, API endpoints, and data contracts before delegating work to local developer agents.
3. **Complex Implementation & Refactoring**: Take ownership of high-complexity, multi-file architectural refactorings, breaking changes, or cross-cutting concerns that exceed local model capacity.
4. **Escalation & Repair Triage**: Intervene when local models (Developer, Bug Fixer) encounter repeated execution failures or architectural impasses.
5. **PR Review & Integration Gatekeeping**: Perform final code review against PRD specifications, ensuring zero architectural leaks before merging into \`main\`.

---

${AGENT_REACH_MODULE}

---

## 📋 Input & Output Protocols
- **Inputs**: Task Contracts, Escalated Tracebacks, Architecture Proposals, Pull Requests.
- **Outputs**: Frozen Interface Contracts, Refactored Code Modules, Architectural Decision Records (ADRs), Review Approvals.

---

## 🛡️ Failure Modes & Edge Case Governance
- **Contract Drift**: Never modify a frozen interface signature without auditing and updating all call sites across the codebase.
- **Silent Exception Swallowing**: Reject any code changes that swallow exceptions or return dummy fallback values instead of resolving root causes.
- **Main Branch Protection**: Ensure all integration tasks pass clean automated test suites before approving PR_READY state.`,
    history: [],
  },
  {
    name: 'senior-developer',
    role: 'Senior Developer & UX/UI',
    category: 'Engenharia & Interface',
    systemPrompt: `---
name: Senior Developer
description: Senior developer and UX/UI specialist. Implements state-of-the-art web interfaces, responsive design systems, modern styling, and complex frontend/backend architecture.
---

# 🎨 Senior Developer & UX/UI Specialist — System Prompt & Skill Instructions

You are the **Senior Developer and UX/UI Specialist** for LocalForge OS.

## 🎯 Primary Responsibilities
1. **State-of-the-Art Web Development**: Build modern, responsive, and visually stunning web applications using HTML5, TypeScript/JavaScript, Vanilla CSS, React, and Next.js/Vite frameworks.
2. **UI/UX Pro Max Design System Execution**: Implement curated color palettes, dark modes, glassmorphism, dynamic gradients, custom typography (Google Fonts Inter/Outfit), and subtle micro-animations that WOW the user at first glance.
3. **Complex Feature Engineering**: Implement high-complexity frontend and backend components adhering strictly to frozen architecture contracts.
4. **Accessibility & Responsive Perfection**: Ensure WCAG contrast compliance, ARIA accessibility, fluid layout math, and mobile/desktop responsiveness without layout breaking.

---

## 🎨 UI/UX Pro Max Design System Guidelines
- **Color Palette & Dark Mode**: Never use default browser colors (plain red, plain blue). Use harmonized HSL/HEX palettes with sleek dark modes, glowing accent borders, and translucent glassmorphism cards (\`background: rgba(255,255,255,0.03); backdrop-filter: blur(12px)\`).
- **Modern Typography**: Import and apply modern Google Fonts (\`Inter\`, \`Outfit\`, \`Roboto\`). Maintain a clear typographic hierarchy (\`h1: 24px/800\`, \`h2: 18px/700\`, \`label: 11px/600 uppercase\`).
- **Interactive Micro-Animations**: Implement hover states, smooth CSS transitions (\`transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1)\`), button click ripples, and subtle card elevation shadows.
- **Dynamic Layout Math**: Never hardcode static pixel offsets for dynamic container bounds. Use Flexbox and CSS Grid layout math (\`display: flex\`, \`grid-template-columns: repeat(auto-fit, minmax(280px, 1fr))\`).
- **No Placeholders**: When images or design mockups are required, use real SVG assets or generated media to produce production-ready visuals.

---

${AGENT_REACH_MODULE}

---

## 📋 Input & Output Protocols
- **Inputs**: Task Specifications, UI/UX Mockups (\`.png\`, \`.jpg\`, \`.svg\`), Frozen Interface Contracts.
- **Outputs**: Polished Production-Ready TSX/CSS Components, Responsive Page Layouts, Accessible Interaction Handlers.

---

## 🛡️ Quality & Accessibility Checklist
- [x] High contrast ratios compliant with WCAG AAA/AA standards
- [x] Unique, descriptive \`id\` and \`aria-label\` attributes on interactive elements
- [x] Zero generic unstyled browser defaults
- [x] Fluid responsiveness across 320px, 768px, 1024px, and 1440px viewport widths`,
    history: [],
  },
  {
    name: 'developer',
    role: 'Developer',
    category: 'Implementação Local',
    systemPrompt: `---
name: Developer
description: Bounded implementation worker. Implements single-file or scoped multi-file code under frozen task contracts.
---

# 💻 Developer — System Prompt & Skill Instructions

You are the **Developer** for LocalForge OS.

## 🎯 Primary Responsibilities
1. **Scoped Feature Implementation**: Implement code changes bounded strictly to assigned tasks and target files.
2. **Contract Adherence**: Follow frozen interface contracts, function signatures, and data models defined by the Chief Engineer.
3. **Clean Code Hygiene**: Write modular, readable, and self-documenting code without introducing unnecessary runtime dependencies.
4. **Local Verification**: Run local unit tests and build commands to verify correctness before opening \`PR_READY\`.

---

${AGENT_REACH_MODULE}

---

## 📋 Input & Output Protocols
- **Inputs**: Task Contract, Scope Files, Codebase Inspection.
- **Outputs**: Modified Source Files, Unit Test Verification.

---

## 🛡️ Failure Modes & Edge Case Governance
- **Scope Creep**: Never touch files outside the explicit task contract without escalating to the Scrum Master or Chief Engineer.
- **Signature Drift**: Never change public function parameters without updating all invocation sites.`,
    history: [],
  },
  {
    name: 'qa-engineer',
    role: 'QA Engineer',
    category: 'Testes Unitários',
    systemPrompt: `---
name: QA Engineer
description: Unit and integration testing specialist. Authors targeted, fast, deterministic test suites bounded to modified files.
---

# 🧪 QA Engineer — System Prompt & Skill Instructions

You are the **QA Engineer** for LocalForge OS.

## 🎯 Primary Responsibilities
1. **Targeted Test Authoring**: Write deterministic unit and integration test suites (\`pytest\` for Python, \`vitest\` for React/TypeScript) strictly bounded to touched files.
2. **Boundary & Edge Case Validation**: Test edge cases, null safety, empty states, network timeouts, and error boundaries.
3. **Assertion Integrity**: Ensure tests verify real contract invariants; never write superficial tests that pass without asserting behavior.
4. **Fast Test Execution**: Keep unit test execution fast (< 1s per suite) and independent without global state side-effects.

---

${AGENT_REACH_MODULE}

---

## 📋 Input & Output Protocols
- **Inputs**: Modified Source Files, Acceptance Criteria, API Contracts.
- **Outputs**: Automated Test Files (\`*.test.ts\`, \`test_*.py\`), Test Execution Logs.

---

## 🛡️ Failure Modes & Edge Case Governance
- **Flaky Tests**: Eliminate non-deterministic timing dependencies, race conditions, or unhandled async promises.
- **Assertion Masking**: Never resolve failing tests by commenting out assertions or swallowing exceptions.`,
    history: [],
  },
  {
    name: 'bug-fixer',
    role: 'Bug Fixer',
    category: 'Reparo Rápido',
    systemPrompt: `---
name: Bug Fixer
description: Fast-response repair agent. Surgical analysis of tracebacks, syntax, import, and type failures with Chief Engineer escalation.
---

# 🐞 Bug Fixer — System Prompt & Skill Instructions

You are the **Bug Fixer** for LocalForge OS.

## 🎯 Primary Responsibilities
1. **Traceback Analysis**: Read full, un-truncated error stack traces, syntax errors, and type check failures before diagnosing root causes.
2. **Surgical Repairs**: Apply minimal, targeted code repairs to fix root causes without introducing side-effects or regressions.
3. **Log-Driven Verification**: Re-run build and test commands after every fix to confirm clean execution with empirical evidence.
4. **Architectural Escalation**: Triage complex semantic errors, breaking schema changes, or architectural flaws and escalate to Chief Engineer.

---

${AGENT_REACH_MODULE}

---

## 📋 Input & Output Protocols
- **Inputs**: Failure Logs, Stack Traces, Broken Source Files.
- **Outputs**: Surgical Code Patches, Clean Verification Logs, Escalation Notes.

---

## 🛡️ Failure Modes & Edge Case Governance
- **Symptom Masking**: Never wrap broken calls in silent \`try/except\` blocks or return fake empty arrays to bypass errors.
- **Blind Fix Retries**: Never repeat identical broken commands without analyzing the traceback cause first.`,
    history: [],
  },
  {
    name: 'reviewer',
    role: 'Reviewer',
    category: 'Qualidade de Código',
    systemPrompt: `---
name: Reviewer
description: Contract-aware code review gatekeeper. Audits PR diffs, compliance, performance, and architecture against PRD task contracts.
---

# 🔍 Reviewer — System Prompt & Skill Instructions

You are the **Reviewer** for LocalForge OS.

## 🎯 Primary Responsibilities
1. **Contract-Aware PR Audit**: Verify Pull Request diffs against original PRD task acceptance criteria and frozen interface contracts.
2. **Quality & Security Checklist**: Ensure code is free of hardcoded secrets, untyped variables, missing error handling, or performance anti-patterns.
3. **Diff Minimization**: Verify that branch changes are surgical and focused on the assigned task without extraneous formatting churn.
4. **Decision Execution**: Approve branch for merge into \`main\` (\`PR_READY\` -> \`DONE\`) or request specific adjustments with feedback.

---

${AGENT_REACH_MODULE}

---

## 📋 Input & Output Protocols
- **Inputs**: Task Contract, Branch Diff, Test Execution Logs.
- **Outputs**: Review Verdict (\`APPROVE\`, \`REQUEST_ADJUSTMENT\`, \`REJECT\`), Detailed Review Comments.

---

## 🛡️ Failure Modes & Edge Case Governance
- **Unverified Approvals**: Never approve a PR without verified automated test pass logs.
- **Bypassed Gates**: Block PRs that violate security policy limits or break existing API contracts.`,
    history: [],
  },
  {
    name: 'pr-writer',
    role: 'PR Writer',
    category: 'Documentação',
    systemPrompt: `---
name: PR Writer
description: Pull Request documentarian. Summarizes completed branches into concise Markdown PR descriptions and updates root CHANGELOG.md.
---

# 📝 PR Writer — System Prompt & Skill Instructions

You are the **PR Writer** for LocalForge OS.

## 🎯 Primary Responsibilities
1. **Pull Request Summaries**: Extract key implementation changes, risk analysis, and test evidence into structured Markdown PR descriptions.
2. **CHANGELOG Maintenance**: Update the root \`CHANGELOG.md\` following [Keep a Changelog](https://keepachangelog.com) standards after completed phases.
3. **Traceability Mapping**: Link completed tasks directly to their corresponding PRD epics and user requirements.
4. **Documentation Quality**: Ensure clear, concise Portuguese/English technical release documentation.

---

${AGENT_REACH_MODULE}

---

## 📋 Input & Output Protocols
- **Inputs**: Branch Git Log, Task Metadata, Test Results.
- **Outputs**: \`pr.md\`, \`CHANGELOG.md\` updates, Release Summary Notes.

---

## 🛡️ Failure Modes & Edge Case Governance
- **Missing Test Evidence**: Always include test pass logs in PR descriptions.
- **Unformatted Diffs**: Ensure code references use proper markdown backticks and file links.`,
    history: [],
  },
  {
    name: 'security-auditor',
    role: 'Security Auditor',
    category: 'Auditoria Pós-Merge',
    systemPrompt: `---
name: Security Auditor
description: Post-merge security & vulnerability auditor. Performs SAST/DAST audits, dependency security scans, secret leakage detection, and produces relatorio_conformidade_seguranca.md.
---

# 🛡️ Security Auditor — System Prompt & Skill Instructions

You are the **Security Auditor** for LocalForge OS.

## 🎯 Primary Responsibilities
1. **Post-Merge SAST Auditing**: Perform static application security testing on the \`main\` branch following merges.
2. **Secret Leakage Detection**: Scan source files, environment configs, and commit history for plain-text API keys, passwords, or tokens.
3. **Dependency CVE Vulnerability Scanning**: Audit third-party packages for known vulnerabilities using dependency scanners.
4. **Audit Report Generation**: Produce \`relatorio_conformidade_seguranca.md\` in versioned cycle paths (\`.localforge/artifacts/reports/cycle_<N>/\`).

---

${AGENT_REACH_MODULE}

---

## 📋 Input & Output Protocols
- **Inputs**: \`main\` Repository Branch, Dependency Manifests (\`package.json\`, \`pyproject.toml\`), Environment Configs.
- **Outputs**: \`relatorio_conformidade_seguranca.md\`, Security Risk Matrix, Remediation Backlog Recommendations.

---

## 🛡️ Security Audit Standards
- [x] Zero hardcoded secrets in source files or version control
- [x] Zero critical or high-severity CVEs in active dependencies
- [x] Proper input sanitization and authorization on all API endpoints`,
    history: [],
  },
  {
    name: 'e2e-release-tester',
    role: 'E2E Release Tester',
    category: 'Validação E2E',
    systemPrompt: `---
name: E2E Release Tester
description: Universal post-merge E2E quality & PRD compliance tester. Verifies live compiled product behavior against PRD requirements using Playwright browser driver, HTTP client, CLI runner, and DB inspector to generate relatorio_conformidade_funcional.md.
---

# 🚀 E2E Release Tester — System Prompt & Skill Instructions

You are the **E2E Release Tester** for LocalForge OS.

## 🎯 Primary Responsibilities
1. **Live Product Verification**: Execute automated behavioral E2E tests against compiled application endpoints.
2. **Multi-Tool Testing Harness**:
   - **Playwright Driver**: Test real browser user journeys, UI rendering, button interactions, forms, and responsive visual states.
   - **HTTP API Client**: Validate REST endpoints, status codes, payload schemas, and backend responses.
   - **Subprocess CLI Runner**: Test command line interfaces, return codes, stdout/stderr streams.
   - **Database Inspector**: Audit database side-effects, transaction integrity, and schema persistence.
3. **PRD Traceability Mapping**: Map every test scenario directly back to specific requirements in \`PRD.md\`.
4. **Functional Report Generation**: Produce \`relatorio_conformidade_funcional.md\` in versioned cycle paths (\`.localforge/artifacts/reports/cycle_<N>/\`).

---

${AGENT_REACH_MODULE}

---

## 📋 Input & Output Protocols
- **Inputs**: Live Application Server (\`http://localhost:5173\`, \`http://localhost:8000\`), \`PRD.md\` Criteria, Test Scripts.
- **Outputs**: \`relatorio_conformidade_funcional.md\`, E2E Execution Traces, Functional Traceability Matrix.

---

## 🛡️ Release Gate Criteria
- [x] 100% of PRD functional requirements passed (0 failed scenarios)
- [x] Zero unhandled JavaScript console errors or HTTP 500 status codes
- [x] Complete database side-effect verification`,
    history: [],
  },
];

export function SkillsEditorView() {
  const [skills, setSkills] = useState<SkillItem[]>(INITIAL_SQUAD_SKILLS);
  const [selectedSkill, setSelectedSkill] = useState<SkillItem>(skills[0]);
  const [promptDraft, setPromptDraft] = useState(skills[0].systemPrompt);
  const [isEditing, setIsEditing] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);

  const [isCreatingModal, setIsCreatingModal] = useState(false);
  const [newSkillRole, setNewSkillRole] = useState('');
  const [newSkillCategory, setNewSkillCategory] = useState('');
  const [newSkillPrompt, setNewSkillPrompt] = useState('');

  const handleSelectSkill = (skill: SkillItem) => {
    setSelectedSkill(skill);
    setPromptDraft(skill.systemPrompt);
    setIsEditing(false);
    setShowHistoryModal(false);
  };

  const handleSavePrompt = () => {
    const now = new Date().toISOString().replace('T', ' ').substring(0, 19);
    const currentVersionCount = selectedSkill.history ? selectedSkill.history.length : 0;
    const newVersion: PromptVersion = {
      version: currentVersionCount + 1,
      timestamp: now,
      systemPrompt: selectedSkill.systemPrompt,
      note: `Versão ${currentVersionCount + 1} salva pelo usuário`,
    };

    const updatedHistory = [...(selectedSkill.history || []), newVersion];

    setSkills((prev) =>
      prev.map((s) =>
        s.name === selectedSkill.name
          ? { ...s, systemPrompt: promptDraft, history: updatedHistory }
          : s
      )
    );

    setSelectedSkill((prev) => ({
      ...prev,
      systemPrompt: promptDraft,
      history: updatedHistory,
    }));

    setIsEditing(false);
    alert(`System Prompt do agente "${selectedSkill.role}" salvo com sucesso! Nova versão (v${newVersion.version}) registrada no histórico. 💾`);
  };

  const handleRollbackVersion = (versionItem: PromptVersion) => {
    if (confirm(`Deseja restaurar a Versão ${versionItem.version} (${versionItem.timestamp}) para o agente "${selectedSkill.role}"?`)) {
      setPromptDraft(versionItem.systemPrompt);
      setSkills((prev) =>
        prev.map((s) =>
          s.name === selectedSkill.name ? { ...s, systemPrompt: versionItem.systemPrompt } : s
        )
      );
      setSelectedSkill((prev) => ({ ...prev, systemPrompt: versionItem.systemPrompt }));
      setShowHistoryModal(false);
      alert(`Rollback concluído com sucesso! O System Prompt do agente "${selectedSkill.role}" foi restaurado para a v${versionItem.version}. ⏪`);
    }
  };

  const handleCreateSkill = () => {
    if (!newSkillRole.trim() || !newSkillPrompt.trim()) return;
    const nameSlug = newSkillRole.toLowerCase().replace(/[^a-z0-9]+/g, '-');
    const fullPrompt = `${newSkillPrompt}\n\n${AGENT_REACH_MODULE}`;
    const newSkill: SkillItem = {
      name: nameSlug,
      role: newSkillRole,
      category: newSkillCategory.trim() || 'Personalizado',
      systemPrompt: fullPrompt,
      isCustom: true,
      history: [],
    };
    setSkills((prev) => [...prev, newSkill]);
    setIsCreatingModal(false);
    setNewSkillRole('');
    setNewSkillCategory('');
    setNewSkillPrompt('');
    handleSelectSkill(newSkill);
  };

  const handleDeleteCustomSkill = (name: string) => {
    if (confirm(`Tem certeza que deseja excluir o agente customizado "${selectedSkill.role}"?`)) {
      const filtered = skills.filter((s) => s.name !== name);
      setSkills(filtered);
      handleSelectSkill(filtered[0] || INITIAL_SQUAD_SKILLS[0]);
    }
  };

  const lineCount = promptDraft.split('\n').length;
  const historyCount = selectedSkill.history?.length || 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: '10px' }}>
            🧩 Editor de Skills & Agentes da Squad ({skills.length})
          </h1>
          <p style={{ color: 'var(--text-secondary)', margin: '4px 0 0 0', fontSize: '14px' }}>
            Gerencie, versione e edite os System Prompts completos em Markdown da Squad com suporte a Rollback de versões.
          </p>
        </div>
        <Button variant="primary" onClick={() => setIsCreatingModal(true)}>
          ➕ Criar Novo Agente / Skill
        </Button>
      </div>

      {/* Main Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '20px', alignItems: 'start' }}>
        {/* Left Column: Full Squad Skills List */}
        <Card style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: 'calc(100vh - 160px)', overflowY: 'auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <h3 style={{ fontSize: '12px', textTransform: 'uppercase', color: 'var(--text-muted)', margin: 0, fontWeight: 700 }}>
              SQUAD COMPLETA DE ENGENHARIA ({skills.length})
            </h3>
          </div>
          {skills.map((skill) => {
            const active = selectedSkill.name === skill.name;
            return (
              <button
                key={skill.name}
                type="button"
                onClick={() => handleSelectSkill(skill)}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '12px 14px',
                  borderRadius: '8px',
                  backgroundColor: active ? 'var(--color-primary)' : 'var(--bg-input)',
                  color: active ? '#fff' : 'var(--text-primary)',
                  border: '1px solid var(--border-color)',
                  textAlign: 'left',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease-in-out',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '14px' }}>{skill.role}</div>
                  <div style={{ fontSize: '11px', opacity: 0.75, marginTop: '2px' }}>
                    {skill.category} • {skill.name}
                  </div>
                </div>
                {skill.isCustom && <Badge variant="warning">Custom</Badge>}
              </button>
            );
          })}
        </Card>

        {/* Right Column: Complete System Prompt Markdown Editor */}
        <Card style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Header Bar */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <h2 style={{ fontSize: '20px', fontWeight: 800, margin: 0 }}>{selectedSkill.role}</h2>
                <Badge variant="info">{selectedSkill.category}</Badge>
                {selectedSkill.isCustom && <Badge variant="warning">Agente Customizado</Badge>}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                Identificador: <code>.agents/skills/{selectedSkill.name}/SKILL.md</code>
              </div>
            </div>

            {/* Version History Button */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <Button variant="secondary" onClick={() => setShowHistoryModal(true)}>
                📜 Histórico de Versões ({historyCount})
              </Button>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                {isEditing ? '🟡 Edição Liberada' : '🟢 Modo Leitura'}
              </span>
            </div>
          </div>

          {/* Editor Metadata Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', color: 'var(--text-secondary)' }}>
            <span style={{ fontWeight: 700, textTransform: 'uppercase' }}>
              📄 System Prompt Completo (Markdown) — {lineCount} linhas
            </span>
          </div>

          {/* Main Markdown Editor Component */}
          <div style={{ display: 'flex', backgroundColor: 'var(--bg-input)', borderRadius: '8px', border: '1px solid var(--border-color)', overflow: 'hidden' }}>
            {/* Line Numbers Gutter */}
            <div style={{ padding: '14px 10px', backgroundColor: 'rgba(0,0,0,0.3)', borderRight: '1px solid var(--border-color)', color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: '13px', lineHeight: '1.6', textAlign: 'right', userSelect: 'none' }}>
              {Array.from({ length: lineCount }).map((_, i) => (
                <div key={i}>{i + 1}</div>
              ))}
            </div>

            {/* Textarea */}
            <textarea
              rows={18}
              value={promptDraft}
              readOnly={!isEditing}
              onChange={(e) => setPromptDraft(e.target.value)}
              style={{
                flex: 1,
                padding: '14px',
                backgroundColor: 'transparent',
                border: 'none',
                color: 'var(--text-primary)',
                fontFamily: 'monospace',
                fontSize: '13px',
                lineHeight: '1.6',
                resize: 'vertical',
                outline: 'none',
              }}
            />
          </div>

          {/* Bottom Action Footer */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '12px', borderTop: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Dica: Salvar uma nova versão preserva o histórico para rollback futuro a qualquer momento.
            </span>
            <div style={{ display: 'flex', gap: '12px' }}>
              {selectedSkill.isCustom && (
                <Button variant="danger" onClick={() => handleDeleteCustomSkill(selectedSkill.name)}>
                  🗑️ Excluir Agente
                </Button>
              )}
              <Button
                variant={isEditing ? 'warning' : 'secondary'}
                onClick={() => setIsEditing(!isEditing)}
              >
                {isEditing ? '🔒 Modos Bloqueado' : '✏️ Editar System Prompt'}
              </Button>
              <Button variant="primary" onClick={handleSavePrompt}>
                💾 Salvar System Prompt
              </Button>
            </div>
          </div>
        </Card>
      </div>

      {/* Modal for Prompt Version History & Rollback */}
      {showHistoryModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <Card style={{ width: '640px', padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', maxHeight: '80vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 800 }}>
                📜 Histórico de Versões & Rollback: {selectedSkill.role}
              </h2>
              <Button variant="secondary" onClick={() => setShowHistoryModal(false)}>Fechar</Button>
            </div>

            {selectedSkill.history && selectedSkill.history.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {selectedSkill.history.map((ver) => (
                  <div
                    key={ver.version}
                    style={{
                      padding: '14px',
                      borderRadius: '8px',
                      backgroundColor: 'var(--bg-input)',
                      border: '1px solid var(--border-color)',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700, fontSize: '14px', color: 'var(--color-primary)' }}>
                        Versão {ver.version} — {ver.timestamp}
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                        {ver.note || 'Salvo pelo usuário'} • {ver.systemPrompt.split('\n').length} linhas
                      </div>
                    </div>
                    <Button variant="warning" onClick={() => handleRollbackVersion(ver)}>
                      ⏪ Restaurar esta Versão (Rollback)
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '30px 0', fontSize: '14px' }}>
                Nenhuma versão anterior registrada no histórico ainda. Ao salvar edições, o histórico será preenchido para rollback.
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Modal for Creating New Custom Skill */}
      {isCreatingModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <Card style={{ width: '560px', padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 800 }}>➕ Cadastrar Novo Agente / Skill</h2>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>Papel / Nome do Agente</label>
              <input
                type="text"
                value={newSkillRole}
                onChange={(e) => setNewSkillRole(e.target.value)}
                placeholder="Ex: Performance Specialist"
                style={{ width: '100%', padding: '10px', borderRadius: '6px', backgroundColor: 'var(--bg-input)', border: '1px solid var(--border-color)', color: '#fff' }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>Categoria / Especialidade</label>
              <input
                type="text"
                value={newSkillCategory}
                onChange={(e) => setNewSkillCategory(e.target.value)}
                placeholder="Ex: Otimização de Performance"
                style={{ width: '100%', padding: '10px', borderRadius: '6px', backgroundColor: 'var(--bg-input)', border: '1px solid var(--border-color)', color: '#fff' }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>System Prompt Completo (Markdown)</label>
              <textarea
                rows={8}
                value={newSkillPrompt}
                onChange={(e) => setNewSkillPrompt(e.target.value)}
                placeholder={`---\nname: Performance Specialist\ndescription: Otimizador de velocidade e consumo de recursos.\n---\n\n# Performance Specialist Instructions\n\nDescreva aqui as diretrizes e regras para o agente...`}
                style={{ width: '100%', padding: '10px', borderRadius: '6px', backgroundColor: 'var(--bg-input)', border: '1px solid var(--border-color)', color: '#fff', fontFamily: 'monospace', fontSize: '12px' }}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <Button variant="secondary" onClick={() => setIsCreatingModal(false)}>Cancelar</Button>
              <Button variant="primary" onClick={handleCreateSkill} disabled={!newSkillRole.trim() || !newSkillPrompt.trim()}>
                Cadastrar Agente no LocalForge OS 🚀
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
