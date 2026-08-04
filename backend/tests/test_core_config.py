import os

import pytest
import yaml
from localforge.core.config import LocalForgeConfig, load_config
from localforge.core.policy import load_policy


def test_config_pydantic_defaults():
    """Verify that LocalForgeConfig instantiates with correct baseline defaults."""
    config = LocalForgeConfig()
    assert config.project.name == "Default Project"
    assert config.git.default_branch == "main"
    assert config.models.provider == "omniroute"
    assert config.models.base_url == "http://localhost:20128/v1"
    assert config.models.default_model == "auto/best-free"
    assert config.chief_engineer.provider == "omniroute"
    assert config.chief_engineer.model == "auto/best-free"


def test_load_config_precedence(tmp_path, monkeypatch):
    """Test loading configuration with priority: CLI > Env > Config File > Defaults."""
    monkeypatch.chdir(tmp_path)

    # 1. Verification of Default config loading
    config = load_config()
    assert config.project.name == "Default Project"

    # 2. Verification of File override
    lf_dir = tmp_path / ".localforge"
    lf_dir.mkdir()
    config_file = lf_dir / "config.yaml"
    file_data = {
        "project": {"name": "File Project"},
        "git": {"default_branch": "develop"},
    }
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(file_data, f)

    config = load_config()
    assert config.project.name == "File Project"
    assert config.git.default_branch == "develop"
    assert config.models.default_model == "auto/best-free"

    # 3. Verification of Env override
    monkeypatch.setenv("LOCALFORGE_PROJECT_NAME", "Env Project")
    config = load_config()
    assert config.project.name == "Env Project"
    assert config.git.default_branch == "develop"

    # 4. Verification of CLI override
    cli_args = {"project_name": "CLI Project", "default_model": "gpt-4o"}
    config = load_config(cli_args=cli_args)
    assert config.project.name == "CLI Project"
    assert config.git.default_branch == "develop"
    assert config.models.default_model == "gpt-4o"


def test_load_config_invalid_yaml(tmp_path, monkeypatch):
    """Test load_config failure when config file has invalid YAML syntax."""
    monkeypatch.chdir(tmp_path)
    lf_dir = tmp_path / ".localforge"
    lf_dir.mkdir()
    config_file = lf_dir / "config.yaml"
    with open(config_file, "w", encoding="utf-8") as f:
        f.write("invalid: yaml: : structure")

    with pytest.raises(ValueError) as exc:
        load_config()
    assert "Failed to parse workspace config" in str(exc.value)


def test_load_config_rejects_direct_inference_provider(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    lf_dir = tmp_path / ".localforge"
    lf_dir.mkdir()
    (lf_dir / "config.yaml").write_text(
        "models:\n  provider: ollama\n  base_url: http://localhost:11434/v1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="OmniRoute-only"):
        load_config()


def test_load_config_rejects_public_gateway_bypass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    lf_dir = tmp_path / ".localforge"
    lf_dir.mkdir()
    (lf_dir / "config.yaml").write_text(
        "models:\n  provider: omniroute\n  base_url: https://api.openrouter.ai/v1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must point to the OmniRoute gateway"):
        load_config()


def test_load_config_rejects_unlisted_private_gateway_bypass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    lf_dir = tmp_path / ".localforge"
    lf_dir.mkdir()
    (lf_dir / "config.yaml").write_text(
        "models:\n  provider: omniroute\n  base_url: http://10.0.0.7:20128/v1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must point to the OmniRoute gateway"):
        load_config()


def test_load_config_reads_safe_local_env_settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "LOCALFORGE_DEFAULT_MODEL=auto/best-coding\n"
        "LOCALFORGE_OMNIROUTE_REQUEST_TIMEOUT=180\n",
        encoding="utf-8",
    )

    config = load_config()

    assert config.models.default_model == "auto/best-coding"


def test_load_config_reads_omniroute_gateway_aliases_without_mutating_environment(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OMNIROUTE_URL", raising=False)
    monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "OMNIROUTE_URL=http://localhost:20128/v1\n"
        "OMNIROUTE_API_KEY=endpoint-key\n",
        encoding="utf-8",
    )

    config = load_config()

    assert config.models.base_url == "http://localhost:20128/v1"
    assert config.chief_engineer.base_url == "http://localhost:20128/v1"
    assert config.models.api_key == "endpoint-key"
    assert config.chief_engineer.api_key == "endpoint-key"
    assert os.getenv("OMNIROUTE_API_KEY") is None


def test_omniroute_client_rejects_direct_provider_endpoint(monkeypatch):
    from localforge.services.omniroute_client import OmniRouteClient

    monkeypatch.setenv("LOCALFORGE_OMNIROUTE_ALLOWED_HOSTS", "")
    with pytest.raises(ValueError, match="must point to the OmniRoute gateway"):
        OmniRouteClient(base_url="https://api.openrouter.ai/v1")


def test_load_config_rejects_direct_fallback_provider(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    lf_dir = tmp_path / ".localforge"
    lf_dir.mkdir()
    (lf_dir / "config.yaml").write_text(
        "chief_engineer:\n  fallback_provider: openrouter\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="fallback_provider"):
        load_config()


def test_load_policy_validation(tmp_path):
    """Test load_policy succeeds with valid YAML and fails on invalid validations."""
    policy_file = tmp_path / "test_policy.yaml"

    # 1. Valid policy check
    policy_data = {
        "version": 1,
        "policy": {
            "name": "unattended_conservative",
            "allowed_commands": ["pytest"],
            "max_repair_attempts": 3,
            "max_files_touched": 5,
        },
    }
    with open(policy_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(policy_data, f)

    policy = load_policy(str(policy_file))
    assert policy.policy.name == "unattended_conservative"
    assert policy.policy.max_repair_attempts == 3

    # 2. Invalid validation (negative repair attempts validation)
    invalid_data = {
        "version": 1,
        "policy": {
            "name": "bad",
            "max_repair_attempts": -1,
        },
    }
    with open(policy_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(invalid_data, f)

    with pytest.raises(ValueError) as exc:
        load_policy(str(policy_file))
    assert "Policy validation failed" in str(exc.value)
