import { useState, useEffect } from 'react';
import { Card } from './Card';
import { Button } from './Button';
import { apiClient } from '../api/client';

export function ModelSettingsView() {
  const [envVars, setEnvVars] = useState<Record<string, string>>({
    LOCALFORGE_DEFAULT_LOCAL_MODEL: 'gemma:2b',
    LOCALFORGE_CHIEF_ENGINEER_MODEL: 'gpt-4o',
    OPENAI_API_KEY: '',
    ANTHROPIC_API_KEY: '',
    GEMINI_API_KEY: '',
  });

  const [localModelMap, setLocalModelMap] = useState<Record<string, string>>({
    'scrum-master': 'gemma:2b',
    developer: 'llama3:8b',
    'bug-fixer': 'gemma:2b',
    'security-auditor': 'gemma:7b',
    'e2e-release-tester': 'gemma:7b',
  });

  const [saving, setSaving] = useState(false);

  useEffect(() => {
    apiClient
      .getEnvSettings()
      .then((vars) => {
        if (vars && Object.keys(vars).length > 0) {
          setEnvVars((prev) => ({ ...prev, ...vars }));
        }
      })
      .catch(() => {
        // Fallback to defaults if env file read fails
      });
  }, []);

  const handleSaveEnv = async () => {
    try {
      setSaving(true);
      await apiClient.updateEnvSettings(envVars);
      alert('Configurações salvas e aplicadas no arquivo .env com sucesso! 🚀');
    } catch (err) {
      alert(`Falha ao salvar configurações: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 800, margin: 0 }}>⚙️ Configurações de Modelos & Ambiente (.env)</h1>
          <p style={{ color: 'var(--text-secondary)', margin: '4px 0 0 0', fontSize: '14px' }}>
            Associe modelos locais (Ollama) e provedores via API para cada agente da Squad.
          </p>
        </div>
        <Button variant="primary" onClick={handleSaveEnv} disabled={saving}>
          {saving ? 'Salvando...' : '💾 Salvar no .env'}
        </Button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        {/* Left Column: Local Models Mapping per Skill */}
        <Card style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <h3 style={{ margin: 0, fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            🖥️ Modelos Locais (Ollama) por Skill
          </h3>

          {Object.entries(localModelMap).map(([skill, model]) => (
            <div key={skill} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '14px', fontWeight: 600 }}>{skill}</span>
              <input
                type="text"
                value={model}
                onChange={(e) => setLocalModelMap((prev) => ({ ...prev, [skill]: e.target.value }))}
                style={{
                  width: '200px',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  backgroundColor: 'var(--bg-input)',
                  border: '1px solid var(--border-color)',
                  color: 'var(--text-primary)',
                  fontSize: '13px',
                }}
              />
            </div>
          ))}
        </Card>

        {/* Right Column: API Keys & Chief Model */}
        <Card style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <h3 style={{ margin: 0, fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            ☁️ Provedores de API & Chaves de Acesso
          </h3>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>
              Modelo do Chief Engineer (API Lead)
            </label>
            <input
              type="text"
              value={envVars.LOCALFORGE_CHIEF_ENGINEER_MODEL || 'gpt-4o'}
              onChange={(e) => setEnvVars((prev) => ({ ...prev, LOCALFORGE_CHIEF_ENGINEER_MODEL: e.target.value }))}
              style={{ width: '100%', padding: '10px', borderRadius: '6px', backgroundColor: 'var(--bg-input)', border: '1px solid var(--border-color)', color: '#fff' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>
              OpenAI API Key
            </label>
            <input
              type="password"
              value={envVars.OPENAI_API_KEY || ''}
              placeholder="sk-..."
              onChange={(e) => setEnvVars((prev) => ({ ...prev, OPENAI_API_KEY: e.target.value }))}
              style={{ width: '100%', padding: '10px', borderRadius: '6px', backgroundColor: 'var(--bg-input)', border: '1px solid var(--border-color)', color: '#fff' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>
              Anthropic API Key
            </label>
            <input
              type="password"
              value={envVars.ANTHROPIC_API_KEY || ''}
              placeholder="sk-ant-..."
              onChange={(e) => setEnvVars((prev) => ({ ...prev, ANTHROPIC_API_KEY: e.target.value }))}
              style={{ width: '100%', padding: '10px', borderRadius: '6px', backgroundColor: 'var(--bg-input)', border: '1px solid var(--border-color)', color: '#fff' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>
              Google Gemini API Key
            </label>
            <input
              type="password"
              value={envVars.GEMINI_API_KEY || ''}
              placeholder="AIzaSy..."
              onChange={(e) => setEnvVars((prev) => ({ ...prev, GEMINI_API_KEY: e.target.value }))}
              style={{ width: '100%', padding: '10px', borderRadius: '6px', backgroundColor: 'var(--bg-input)', border: '1px solid var(--border-color)', color: '#fff' }}
            />
          </div>
        </Card>
      </div>
    </div>
  );
}
