import { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { Button } from './Button';
import { Card } from './Card';

const ROUTE_FIELDS = [
  {
    key: 'LOCALFORGE_DEFAULT_MODEL',
    label: 'Squad default route',
    fallback: 'auto/best-free',
    description: 'Fast free or freemium route for bounded work.',
  },
  {
    key: 'LOCALFORGE_CHIEF_MODEL',
    label: 'Chief Engineer route',
    fallback: 'auto/coding:free',
    description: 'High-capability route for architecture and recovery.',
  },
] as const;

export function ModelSettingsView() {
  const [envVars, setEnvVars] = useState<Record<string, string>>({
    LOCALFORGE_DEFAULT_MODEL: 'auto/best-free',
    LOCALFORGE_CHIEF_MODEL: 'auto/coding:free',
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    apiClient
      .getEnvSettings()
      .then((vars) => setEnvVars((current) => ({ ...current, ...vars })))
      .catch(() => undefined);
  }, []);

  const handleSave = async () => {
    try {
      setSaving(true);
      await apiClient.updateEnvSettings(envVars);
      window.alert('OmniRoute settings saved.');
    } catch (error) {
      window.alert(`Unable to save settings: ${error}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0 }}>OmniRoute routing</h1>
          <p style={{ color: 'var(--text-secondary)', margin: '4px 0 0', fontSize: 14 }}>
            Every Squad inference call is routed through the ForgeOS OmniRoute gateway.
          </p>
        </div>
        <Button variant="primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save routes'}
        </Button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
        {ROUTE_FIELDS.map((field) => (
          <Card key={field.key} style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <label htmlFor={field.key} style={{ fontSize: 14, fontWeight: 700 }}>
              {field.label}
            </label>
            <input
              id={field.key}
              type="text"
              value={envVars[field.key] || field.fallback}
              onChange={(event) =>
                setEnvVars((current) => ({ ...current, [field.key]: event.target.value }))
              }
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: 6,
                backgroundColor: 'var(--bg-input)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-primary)',
                fontSize: 13,
              }}
            />
            <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{field.description}</span>
          </Card>
        ))}
      </div>

      <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: 0 }}>
        Provider credentials and upstream connections are managed inside OmniRoute and are never stored by this panel.
      </p>
    </div>
  );
}
