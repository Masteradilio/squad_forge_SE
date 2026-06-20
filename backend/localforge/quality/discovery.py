import json
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class DiscoveredCommand:
    command: str
    source: str


class TestCommandDiscovery:
    def discover(self, project_root: str | Path) -> list[DiscoveredCommand]:
        root = Path(project_root)
        commands: list[DiscoveredCommand] = []
        commands.extend(self._load_overrides(root))

        if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists():
            commands.append(DiscoveredCommand("python -m pytest", "python"))
            commands.append(DiscoveredCommand("ruff check .", "python"))
            commands.append(DiscoveredCommand("mypy .", "python"))

        package_json = root / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
            scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
            if isinstance(scripts, dict):
                if "test" in scripts:
                    commands.append(DiscoveredCommand("npm test", "package.json"))
                if "lint" in scripts:
                    commands.append(DiscoveredCommand("npm run lint", "package.json"))
                if "typecheck" in scripts:
                    commands.append(DiscoveredCommand("npm run typecheck", "package.json"))
            if (root / "pnpm-lock.yaml").exists():
                commands.append(DiscoveredCommand("pnpm test", "package.json"))
            if (root / "tsconfig.json").exists():
                commands.append(DiscoveredCommand("npx tsc --noEmit", "typescript"))

        return self._dedupe(commands)

    def _load_overrides(self, root: Path) -> list[DiscoveredCommand]:
        config_path = root / ".localforge" / "config.yaml"
        if not config_path.exists():
            return []
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            return []
        if not isinstance(data, dict):
            return []
        quality = data.get("quality", {})
        if not isinstance(quality, dict):
            return []
        raw_commands = quality.get("test_commands", [])
        if not isinstance(raw_commands, list):
            return []
        return [
            DiscoveredCommand(command, "localforge config")
            for command in raw_commands
            if isinstance(command, str) and command.strip()
        ]

    def _dedupe(self, commands: list[DiscoveredCommand]) -> list[DiscoveredCommand]:
        seen: set[str] = set()
        result: list[DiscoveredCommand] = []
        for command in commands:
            if command.command not in seen:
                seen.add(command.command)
                result.append(command)
        return result
