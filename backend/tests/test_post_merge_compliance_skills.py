from pathlib import Path

from localforge.skills.registry import SkillRegistry


def test_post_merge_compliance_skills_registered():
    """Verify security-auditor and e2e-release-tester skills are registered in SkillRegistry."""
    registry = SkillRegistry(project_root=".")
    all_skills = registry.load_all()
    skill_names = {skill.name for skill in all_skills}

    assert "security-auditor" in skill_names
    assert "e2e-release-tester" in skill_names


def test_security_auditor_skill_definition():
    """Verify security-auditor definition attributes and expected artifacts."""
    registry = SkillRegistry(project_root=".")
    all_skills = registry.load_all()
    sec_skill = next(s for s in all_skills if s.name == "security-auditor")

    assert "relatorio_conformidade_seguranca.md" in sec_skill.expected_artifacts
    assert "security" in sec_skill.triggers
    assert "audit" in sec_skill.triggers
    assert "scan secrets" in sec_skill.allowed_actions


def test_e2e_release_tester_skill_definition():
    """Verify e2e-release-tester definition attributes, triggers, and expected artifacts."""
    registry = SkillRegistry(project_root=".")
    all_skills = registry.load_all()
    tester_skill = next(s for s in all_skills if s.name == "e2e-release-tester")

    assert "relatorio_conformidade_funcional.md" in tester_skill.expected_artifacts
    assert "e2e" in tester_skill.triggers
    assert "compliance" in tester_skill.triggers
    assert "browser automation" in tester_skill.allowed_actions


def test_skill_markdown_files_exist():
    """Verify markdown system prompt SKILL.md files exist on disk for both skills."""
    sec_skill_path = Path(".agents/skills/security-auditor/SKILL.md")
    tester_skill_path = Path(".agents/skills/e2e-release-tester/SKILL.md")

    assert sec_skill_path.exists()
    assert tester_skill_path.exists()

    sec_content = sec_skill_path.read_text(encoding="utf-8")
    tester_content = tester_skill_path.read_text(encoding="utf-8")

    assert "relatorio_conformidade_seguranca.md" in sec_content
    assert "relatorio_conformidade_funcional.md" in tester_content
    assert "cycle_<N>" in sec_content
    assert "cycle_<N>" in tester_content
    assert "Playwright" in tester_content
    assert "SAST" in sec_content
