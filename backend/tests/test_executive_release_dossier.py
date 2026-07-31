from pathlib import Path
from localforge.prd.dossier import (
    build_executive_release_dossier,
    calculate_file_sha256,
    render_executive_release_dossier_markdown,
    scan_cycle_reports,
)


def test_calculate_file_sha256(tmp_path: Path):
    """Test SHA-256 calculation for a compiled file artifact."""
    test_file = tmp_path / "compiled_app.html"
    test_file.write_text("<html><body>HP 12C Platinum App</body></html>", encoding="utf-8")

    checksum = calculate_file_sha256(test_file)
    assert len(checksum) == 64
    assert checksum != "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_scan_cycle_reports(tmp_path: Path):
    """Test scanning historical cycle directories for convergence summaries."""
    reports_dir = tmp_path / "reports"
    c1 = reports_dir / "cycle_1"
    c2 = reports_dir / "cycle_2"
    c1.mkdir(parents=True)
    c2.mkdir(parents=True)

    (c1 / "relatorio_conformidade_seguranca.md").write_text("INCONFORME [SECP-001]", encoding="utf-8")
    (c1 / "relatorio_conformidade_funcional.md").write_text("INCONFORME [NCF-001] [NCF-002]", encoding="utf-8")

    (c2 / "relatorio_conformidade_seguranca.md").write_text("CONFORME", encoding="utf-8")
    (c2 / "relatorio_conformidade_funcional.md").write_text("CONFORME", encoding="utf-8")

    summaries = scan_cycle_reports(reports_dir)
    assert len(summaries) == 2
    assert summaries[0].cycle_name == "cycle_1"
    assert summaries[0].security_issues_count == 1
    assert summaries[0].functional_issues_count == 2

    assert summaries[1].cycle_name == "cycle_2"
    assert summaries[1].security_issues_count == 0
    assert summaries[1].functional_issues_count == 0


def test_build_and_render_executive_release_dossier(tmp_path: Path):
    """Test building and rendering the full Executive Release Dossier markdown."""
    reports_dir = tmp_path / "reports"
    c1 = reports_dir / "cycle_1"
    c1.mkdir(parents=True)
    (c1 / "relatorio_conformidade_seguranca.md").write_text("CONFORME", encoding="utf-8")
    (c1 / "relatorio_conformidade_funcional.md").write_text("CONFORME", encoding="utf-8")

    bundle = tmp_path / "hp12c.html"
    bundle.write_text("HP12C Final Product", encoding="utf-8")

    dossier = build_executive_release_dossier(
        project_name="HP 12C Platinum Financial Calculator",
        compiled_bundle_path=str(bundle),
        reports_dir=reports_dir,
    )

    assert dossier.project_name == "HP 12C Platinum Financial Calculator"
    assert dossier.total_cycles_count == 1
    assert dossier.final_compliance_status == "CONFORME 🟢"
    assert dossier.security_signoff is True
    assert dossier.functional_signoff is True

    md_output = render_executive_release_dossier_markdown(dossier)
    assert "Dossiê Executivo de Liberação — HP 12C Platinum Financial Calculator" in md_output
    assert "Checksum SHA-256 do Produto" in md_output
    assert "Curva de Convergência dos Ciclos de Qualidade" in md_output
    assert "cycle_1" in md_output
