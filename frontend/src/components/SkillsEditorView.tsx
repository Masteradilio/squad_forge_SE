import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient, type SkillDefinition } from '../api/client';
import { Badge } from './Badge';
import { Button } from './Button';
import { Card } from './Card';
import { ResourceState, type ResourceStatus } from './ResourceState';

interface SkillsEditorViewProps {
  projectId?: number;
}

function statusCopy(status: ResourceStatus, error?: string | null) {
  switch (status) {
    case 'loading':
      return { title: 'Carregando skills reais', message: 'Consultando o registry persistido do projeto.' };
    case 'empty':
      return { title: 'Nenhuma skill registrada', message: 'A API respondeu sem skills para este projeto.' };
    case 'error':
      return { title: 'Skills indisponíveis', message: error ? `A consulta falhou: ${error}` : 'A consulta ao registry falhou.' };
    case 'blocked':
      return { title: 'Skills bloqueadas', message: 'Selecione um projeto ativo para consultar o registry real.' };
    case 'ready':
      return null;
  }
}

function skillPayload(skill: SkillDefinition, systemPrompt: string): Partial<SkillDefinition> {
  return {
    name: skill.name,
    purpose: skill.purpose,
    system_prompt: systemPrompt,
    triggers: skill.triggers,
    allowed_actions: skill.allowed_actions,
    expected_artifacts: skill.expected_artifacts,
    failure_modes: skill.failure_modes,
    examples: skill.examples,
    strategy: skill.strategy,
    max_retries: skill.max_retries,
    context_budget: skill.context_budget,
    runtime: skill.runtime,
    entrypoint: skill.entrypoint,
    permissions: skill.permissions,
    dependencies: skill.dependencies,
    manifest_version: skill.manifest_version,
    enabled: skill.enabled,
  };
}

export function SkillsEditorView({ projectId }: SkillsEditorViewProps) {
  const [skills, setSkills] = useState<SkillDefinition[]>([]);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [promptDraft, setPromptDraft] = useState('');
  const [status, setStatus] = useState<ResourceStatus>('blocked');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newPurpose, setNewPurpose] = useState('');
  const [newPrompt, setNewPrompt] = useState('');

  const selectedSkill = useMemo(
    () => skills.find((skill) => skill.name === selectedName) ?? null,
    [selectedName, skills],
  );

  const loadSkills = useCallback(async () => {
    if (!projectId) {
      setSkills([]);
      setSelectedName(null);
      setPromptDraft('');
      setError(null);
      setStatus('blocked');
      return;
    }

    setStatus('loading');
    setError(null);
    try {
      const data = await apiClient.fetchSkills(projectId);
      setSkills(data);
      setSelectedName((current) => current && data.some((skill) => skill.name === current) ? current : data[0]?.name ?? null);
      setPromptDraft(data[0]?.system_prompt ?? '');
      setStatus(data.length > 0 ? 'ready' : 'empty');
    } catch (reason: unknown) {
      setSkills([]);
      setSelectedName(null);
      setPromptDraft('');
      setStatus('error');
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [projectId]);

  useEffect(() => {
    // This effect synchronizes the editor with the persisted skill registry.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadSkills();
  }, [loadSkills]);

  const selectSkill = (skill: SkillDefinition) => {
    setSelectedName(skill.name);
    setPromptDraft(skill.system_prompt ?? '');
    setIsCreating(false);
  };

  const saveSkill = async () => {
    if (!projectId || !selectedSkill) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await apiClient.updateSkill(projectId, selectedSkill.name, skillPayload(selectedSkill, promptDraft));
      setSkills((current) => current.map((skill) => skill.name === updated.name ? updated : skill));
      setPromptDraft(updated.system_prompt ?? '');
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  };

  const createSkill = async () => {
    if (!projectId || !newName.trim() || !newPrompt.trim()) return;
    const name = newName.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    if (!name) {
      setError('O nome da skill precisa conter caracteres alfanuméricos.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await apiClient.createSkill(projectId, {
        name,
        purpose: newPurpose.trim() || 'Skill personalizada',
        system_prompt: newPrompt,
        triggers: [newName.trim()],
        allowed_actions: [],
        expected_artifacts: [],
        failure_modes: [],
        examples: [],
        runtime: 'instruction',
        permissions: [],
        dependencies: [],
        manifest_version: 1,
      });
      setSkills((current) => [...current, created]);
      setSelectedName(created.name);
      setPromptDraft(created.system_prompt ?? '');
      setNewName('');
      setNewPurpose('');
      setNewPrompt('');
      setIsCreating(false);
      setStatus('ready');
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  };

  const deleteSkill = async () => {
    if (!projectId || !selectedSkill || selectedSkill.source !== 'local') return;
    if (!window.confirm(`Excluir a skill persistida "${selectedSkill.name}"?`)) return;
    setDeleting(true);
    setError(null);
    try {
      await apiClient.deleteSkill(projectId, selectedSkill.name);
      const remaining = skills.filter((skill) => skill.name !== selectedSkill.name);
      setSkills(remaining);
      setSelectedName(remaining[0]?.name ?? null);
      setPromptDraft(remaining[0]?.system_prompt ?? '');
      setStatus(remaining.length > 0 ? 'ready' : 'empty');
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setDeleting(false);
    }
  };

  const state = statusCopy(status, error);

  return (
    <section data-testid="skills-view" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 800, margin: 0 }}>Editor de Skills &amp; Agentes ({skills.length})</h1>
          <p style={{ color: 'var(--text-secondary)', margin: '4px 0 0', fontSize: '14px' }}>
            Registry real do projeto; prompts ausentes permanecem ausentes e não são preenchidos por fallback.
          </p>
        </div>
        <Button variant="primary" disabled={!projectId} onClick={() => setIsCreating(true)}>
          Criar skill persistida
        </Button>
      </div>

      {status !== 'ready' && state && <ResourceState status={status} title={state.title} message={state.message} testId={`skills-state-${status}`} />}
      {error && status === 'ready' && <ResourceState status="error" title="Operação não concluída" message={error} testId="skills-operation-error" />}

      {status === 'ready' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 320px) minmax(0, 1fr)', gap: '20px', alignItems: 'start' }}>
          <Card title="Skills registradas" testId="skills-list" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {skills.map((skill) => (
                <button
                  key={skill.name}
                  type="button"
                  data-testid={`skill-item-${skill.name}`}
                  aria-pressed={selectedName === skill.name}
                  onClick={() => selectSkill(skill)}
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', padding: '10px 12px', borderRadius: '8px', backgroundColor: selectedName === skill.name ? 'var(--color-primary)' : 'var(--bg-input)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', textAlign: 'left', cursor: 'pointer' }}
                >
                  <span><strong>{skill.name}</strong><br /><small>{skill.purpose}</small></span>
                  <Badge variant={skill.source === 'local' ? 'warning' : 'info'}>{skill.source}</Badge>
                </button>
              ))}
            </div>
          </Card>

          <Card title={selectedSkill ? `Skill: ${selectedSkill.name}` : 'Nenhuma skill selecionada'} testId="skill-editor" style={{ padding: '20px' }}>
            {selectedSkill ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  <Badge variant="info">source: {selectedSkill.source}</Badge>
                  <Badge variant={selectedSkill.enabled === false ? 'muted' : 'success'}>{selectedSkill.enabled === false ? 'disabled' : 'enabled'}</Badge>
                  {selectedSkill.runtime && <Badge variant="muted">runtime: {selectedSkill.runtime}</Badge>}
                </div>
                {selectedSkill.system_prompt ? (
                  <textarea
                    data-testid="skill-prompt-editor"
                    aria-label={`System prompt ${selectedSkill.name}`}
                    rows={20}
                    value={promptDraft}
                    onChange={(event) => setPromptDraft(event.target.value)}
                    style={{ width: '100%', padding: '14px', borderRadius: '8px', backgroundColor: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', fontFamily: 'monospace', fontSize: '13px', lineHeight: 1.5, resize: 'vertical' }}
                  />
                ) : (
                  <ResourceState status="empty" title="System prompt não fornecido" message="O backend não retornou um prompt para esta skill; nenhum conteúdo foi inventado." testId="skill-prompt-state-empty" />
                )}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', flexWrap: 'wrap' }}>
                  {selectedSkill.source === 'local' && <Button variant="danger" disabled={deleting} onClick={() => void deleteSkill()}>{deleting ? 'Excluindo...' : 'Excluir skill'}</Button>}
                  <Button variant="primary" disabled={saving || selectedSkill.system_prompt === undefined} onClick={() => void saveSkill()}>{saving ? 'Salvando...' : 'Salvar prompt'}</Button>
                </div>
              </div>
            ) : (
              <ResourceState status="empty" title="Nenhuma skill selecionada" message="Selecione um registro retornado pela API." testId="skill-editor-state-empty" />
            )}
          </Card>
        </div>
      )}

      {isCreating && (
        <Card title="Nova skill persistida" testId="skill-create-form" style={{ padding: '20px' }}>
          <div style={{ display: 'grid', gap: '12px' }}>
            <input aria-label="Nome da skill" value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="Nome da skill" />
            <input aria-label="Propósito da skill" value={newPurpose} onChange={(event) => setNewPurpose(event.target.value)} placeholder="Propósito" />
            <textarea aria-label="Prompt da nova skill" rows={8} value={newPrompt} onChange={(event) => setNewPrompt(event.target.value)} placeholder="System prompt fornecido pelo usuário" />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <Button variant="secondary" onClick={() => setIsCreating(false)}>Cancelar</Button>
              <Button variant="primary" disabled={saving || !newName.trim() || !newPrompt.trim()} onClick={() => void createSkill()}>Persistir skill</Button>
            </div>
          </div>
        </Card>
      )}
    </section>
  );
}
