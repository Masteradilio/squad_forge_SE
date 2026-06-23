# LocalForge Skill File Format

Local project skills live under `.localforge/skills/*.json`.

Required fields:

- `name`: stable skill identifier.
- `purpose`: short description of when the procedure helps.
- `triggers`: keywords matched against task metadata and project stack.
- `allowed_actions`: bounded actions the skill may guide.
- `expected_artifacts`: artifacts the skill should produce or inspect.
- `failure_modes`: known ways the procedure can fail.
- `examples`: concise usage examples.

Example:

```json
{
  "name": "sqlite-migration",
  "purpose": "Plan SQLite migrations safely.",
  "triggers": ["sqlite", "migration"],
  "allowed_actions": ["read schema", "write additive migration"],
  "expected_artifacts": ["risk.md"],
  "failure_modes": ["missing rollback", "destructive column change"],
  "examples": ["Add nullable columns before enforcing new constraints."]
}
```

Built-in skills are loaded first. Local skills with the same `name` override a
built-in entry.
