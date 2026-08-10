import pytest
from fastapi.testclient import TestClient
from localforge.api.app import create_app
from localforge.core.config import LocalForgeConfig, ReleaseConfig
from localforge.services.operational_profiles import (
    available_profile_manifest,
    normalize_profile_names,
    profile_manifest,
)


def test_operational_profiles_are_deterministic_and_deduplicated() -> None:
    assert normalize_profile_names(["full-coverage", "saas", "full_coverage"]) == [
        "full_coverage",
        "saas",
    ]
    manifest = profile_manifest(["saas"])
    assert manifest["selected_profiles"] == ["saas"]
    assert "context7" in [item["key"] for item in manifest["capabilities"]]
    assert "tenant_key_vault" in [item["key"] for item in manifest["capabilities"]]


def test_unknown_operational_profile_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unknown operational profile"):
        normalize_profile_names(["does-not-exist"])


def test_release_snapshot_keeps_optional_gates_explicit() -> None:
    config = ReleaseConfig(
        operational_profiles=["reference", "full_coverage"],
        require_release_tree_audit=True,
        require_semantic_review=True,
    )
    assert config.operational_profiles == ["reference", "full_coverage"]
    assert config.require_release_tree_audit is True
    assert config.require_semantic_review is True
    assert LocalForgeConfig().release.require_semantic_review is False


def test_available_manifest_describes_external_boundaries_without_running_them() -> None:
    manifest = available_profile_manifest()
    assert {"reference", "full_coverage", "saas"}.issubset(
        set(manifest["selected_profiles"])
    )
    kubernetes = next(
        item for item in manifest["capabilities"] if item["key"] == "kubernetes_helm"
    )
    assert kubernetes["requires_external_service"] is True


def test_operational_profile_and_status_api_boundaries(db_manager) -> None:
    with TestClient(create_app(db_manager=db_manager)) as client:
        profiles = client.get("/capabilities/operational-profiles")
        assert profiles.status_code == 200
        assert "full_coverage" in profiles.json()["selected_profiles"]

        status = client.get("/operations/status?project_id=1")
        assert status.status_code == 200
        assert {"status", "queue_depth", "total_cost_usd"}.issubset(status.json())
