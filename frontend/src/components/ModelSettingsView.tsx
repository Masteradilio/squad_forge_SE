import { useCallback, useEffect, useState } from 'react';
import { apiClient, type ModelRoute } from '../api/client';
import { Badge, StatusBadge } from './Badge';
import { Button } from './Button';
import { Card } from './Card';
import { ResourceState, type ResourceStatus } from './ResourceState';

interface ModelSettingsViewProps {
  projectId?: number;
}

const ROUTE_FIELDS = [
  {
    key: 'LOCALFORGE_DEFAULT_MODEL',
    label: 'Squad default route',
    description: 'Rota configurada para chamadas padrão da Squad.',
  },
  {
    key: 'LOCALFORGE_CHIEF_MODEL',
    label: 'Chief Engineer route',
    description: 'Rota configurada para decisões de arquitetura e recuperação.',
  },
] as const;

function stateCopy(status: ResourceStatus, resource: string) {
  switch (status) {
    case 'loading':
      return { title: `Carregando ${resource}`, message: 'Consultando configuração real da API.' };
    case 'empty':
      return { title: `${resource} não configurado`, message: 'A API respondeu sem registros configurados.' };
    case 'error':
      return { title: `${resource} indisponível`, message: 'A consulta falhou; nenhum valor padrão foi inventado.' };
    case 'blocked':
      return { title: `${resource} bloqueado`, message: 'Selecione um projeto ativo para consultar este recurso.' };
    case 'ready':
      return null;
  }
}

export function ModelSettingsView({ projectId }: ModelSettingsViewProps) {
  const [envVars, setEnvVars] = useState<Record<string, string>>({});
  const [routes, setRoutes] = useState<ModelRoute[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [envStatus, setEnvStatus] = useState<ResourceStatus>('loading');
  const [routesStatus, setRoutesStatus] = useState<ResourceStatus>('blocked');
  const [modelsStatus, setModelsStatus] = useState<ResourceStatus>('loading');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    setEnvStatus('loading');
    setModelsStatus('loading');
    if (projectId) setRoutesStatus('loading');
    else setRoutesStatus('blocked');
    setError(null);

    const envResult = await apiClient.getEnvSettings().then((value) => ({ ok: true as const, value })).catch((reason: unknown) => ({ ok: false as const, reason }));
    if (envResult.ok) {
      setEnvVars(envResult.value);
      setEnvStatus(Object.keys(envResult.value).length > 0 ? 'ready' : 'empty');
    } else {
      setEnvStatus('error');
      setError(envResult.reason instanceof Error ? envResult.reason.message : String(envResult.reason));
    }

    const modelsResult = await apiClient.fetchModels().then((value) => ({ ok: true as const, value })).catch((reason: unknown) => ({ ok: false as const, reason }));
    if (modelsResult.ok) {
      setModels(modelsResult.value.models);
      setModelsStatus(modelsResult.value.models.length > 0 ? 'ready' : 'empty');
    } else {
      setModelsStatus('error');
      setError(modelsResult.reason instanceof Error ? modelsResult.reason.message : String(modelsResult.reason));
    }

    if (projectId) {
      const routesResult = await apiClient.fetchModelRoutes(projectId).then((value) => ({ ok: true as const, value })).catch((reason: unknown) => ({ ok: false as const, reason }));
      if (routesResult.ok) {
        setRoutes(routesResult.value);
        setRoutesStatus(routesResult.value.length > 0 ? 'ready' : 'empty');
      } else {
        setRoutesStatus('error');
        setError(routesResult.reason instanceof Error ? routesResult.reason.message : String(routesResult.reason));
      }
    } else {
      setRoutes([]);
    }
  }, [projectId]);

  useEffect(() => {
    // This effect synchronizes routing settings with external API state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadSettings();
  }, [loadSettings]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const saved = await apiClient.updateEnvSettings(envVars);
      setEnvVars(saved);
      setEnvStatus(Object.keys(saved).length > 0 ? 'ready' : 'empty');
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  };

  const renderState = (status: ResourceStatus, resource: string, testId: string) => {
    if (status === 'ready') return null;
    const copy = stateCopy(status, resource);
    return copy ? <ResourceState status={status} title={copy.title} message={error && status === 'error' ? `${copy.message} ${error}` : copy.message} testId={testId} /> : null;
  };

  return (
    <section data-testid="model-routing-view" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0 }}>OmniRoute routing</h1>
          <p style={{ color: 'var(--text-secondary)', margin: '4px 0 0', fontSize: 14 }}>
            Rotas, modelos e variáveis exibidos somente quando retornados pela API.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Button variant="secondary" onClick={() => void loadSettings()}>Atualizar</Button>
          <Button variant="primary" onClick={() => void handleSave()} disabled={saving || envStatus === 'loading'}>
            {saving ? 'Salvando...' : 'Salvar variáveis'}
          </Button>
        </div>
      </div>

      {envStatus !== 'ready' && renderState(envStatus, 'variáveis de rota', 'model-env-state')}
      {error && envStatus === 'ready' && <ResourceState status="error" title="Operação não concluída" message={error} testId="model-operation-error" />}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
        {ROUTE_FIELDS.map((field) => (
          <Card key={field.key} style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <label htmlFor={field.key} style={{ fontSize: 14, fontWeight: 700 }}>{field.label}</label>
            <input
              id={field.key}
              data-testid={`model-env-${field.key}`}
              type="text"
              value={envVars[field.key] ?? ''}
              onChange={(event) => setEnvVars((current) => ({ ...current, [field.key]: event.target.value }))}
              placeholder="Não configurado pela API"
              style={{ width: '100%', padding: '10px 12px', borderRadius: 6, backgroundColor: 'var(--bg-input)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', fontSize: 13 }}
            />
            <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{field.description}</span>
          </Card>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
        <Card title="Model routes do projeto" testId="model-routes-panel">
          {routesStatus !== 'ready' ? renderState(routesStatus, 'model routes', 'model-routes-state') : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {routes.map((route) => (
                <div key={route.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                  <span><strong>{route.role}</strong><br /><small style={{ color: 'var(--text-secondary)' }}>{route.provider} / {route.model_profile_id}</small></span>
                  <Badge variant="info">configured</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Modelos retornados pelo provider" testId="available-models-panel">
          {modelsStatus !== 'ready' ? renderState(modelsStatus, 'modelos', 'available-models-state') : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {models.map((model) => <Badge key={model} variant="muted">{model}</Badge>)}
            </div>
          )}
        </Card>
      </div>

      <Card title="Estado das rotas persistidas" testId="model-routing-status">
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <StatusBadge status={routesStatus} />
          <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
            {routesStatus === 'ready' ? `${routes.length} rota(s) retornada(s)` : 'Nenhuma rota é inferida quando o backend não responde.'}
          </span>
        </div>
      </Card>
    </section>
  );
}
