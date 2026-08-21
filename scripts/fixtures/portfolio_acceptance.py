# -*- coding: utf-8 -*-
from pathlib import Path
import pytest

def test_portfolio_structure_and_projects():
    candidate_roots = [
        Path.cwd(),
        Path(__file__).resolve().parents[1],
        Path(__file__).resolve().parents[2] / "benchmarks" / "workspaces" / "portfolio-masteradilio",
        Path(__file__).resolve().parents[2] / "samples" / "e2e-portfolio-masteradilio",
    ]
    index_path = None
    for root in candidate_roots:
        candidates = [
            root / "index.html",
            root / "app" / "index.html",
            root / "public" / "index.html",
            root / "dist" / "index.html",
            root / "src" / "index.html",
        ]
        index_path = next((p for p in candidates if p.is_file()), None)
        if index_path is not None:
            break

    assert index_path is not None, "Portfolio index.html must be generated in workspace."
    
    html = index_path.read_text(encoding="utf-8")
    
    # 1. Identity & Hero Checks
    assert "Adilio Farias" in html, "Must present Adilio Farias in the hero/header."
    assert any(term in html.lower() for term in ["data scientist", "ai engineer", "machine learning"]), "Must highlight Senior Data Scientist and AI/ML role."
    assert "github.com/Masteradilio" in html, "Must contain link to https://github.com/Masteradilio."
    assert "linkedin.com/in/adiliofarias" in html or "linkedin" in html.lower(), "Must contain LinkedIn profile reference."
    
    # 2. Key 7 GitHub Projects Presence
    required_projects = [
        "squad_forge",
        "time_series_predict",
        "ontology_rag_guardrail",
        "rag_agent_datasus",
        "credit_risk_model",
        "credit_scoring_model",
        "sentinel_pix",
    ]
    for proj in required_projects:
        assert proj.lower() in html.lower(), f"Project '{proj}' must be presented in the showcase grid."
        
    # 3. Bilingual Language Selector Presence (PT-BR and English)
    assert any(term in html.lower() for term in ["pt-br", "en", "idioma", "language", "switchlang"]), "Must provide a language switcher for PT-BR and English."
    
    # 4. Squad Forge SE Autonomous Process Breakdown
    assert "squad forge se" in html.lower() or "squad_forge_se" in html.lower(), "Must highlight Squad Forge SE generation."
    assert any(term in html.lower() for term in ["scrum master", "chief engineer", "llama.cpp", "qwen"]), "Must explain Squad Forge SE roles/model step-by-step."
    
    # 5. Mobile Responsiveness & Layout
    assert "viewport" in html, "Must have viewport meta tag for mobile devices."
    assert any(cls in html for cls in ["md:", "lg:", "sm:"]), "Must use responsive CSS grid/flexbox breakpoints."

    # 6. AI Assistant & RAG Interface
    assert "chat-box" in html, "Must contain interactive chat-box for AI assistant."
    assert any(term in html.lower() for term in ["assistente", "assistant"]), "Must contain interactive assistant about Adilio Farias."

    # 7. CV Download Buttons & Assets
    assert "cv_adilio_farias_pt.html" in html, "Must provide download/view link for Portuguese CV."
    assert "cv_adilio_farias_en.html" in html, "Must provide download/view link for English Resume."


def test_portfolio_assets_and_dist_package():
    repo_root = Path(__file__).resolve().parents[2]
    assets_dir = repo_root / "samples" / "e2e-portfolio-masteradilio" / "assets"
    assert assets_dir.is_dir(), "assets directory must exist in samples/e2e-portfolio-masteradilio."
    
    expected_assets = [
        "cv_adilio_farias_pt.html",
        "cv_adilio_farias_en.html",
        "cv_adilio_farias_pt.txt",
        "cv_adilio_farias_en.txt",
    ]
    for asset in expected_assets:
        asset_file = assets_dir / asset
        assert asset_file.is_file(), f"Asset {asset} must exist in assets/."
        assert asset_file.stat().st_size > 500, f"Asset {asset} must not be empty."

    # Verify dist/masteradilio.github.io package
    dist_dir = repo_root / "dist" / "masteradilio.github.io"
    assert dist_dir.is_dir(), "dist/masteradilio.github.io must exist for direct git deployment."
    assert (dist_dir / "index.html").is_file(), "dist index.html must exist."
    assert (dist_dir / "assets" / "cv_adilio_farias_pt.html").is_file(), "dist assets must be populated."

    # Verify serverless worker
    worker_file = repo_root / "serverless" / "cloudflare-worker" / "src" / "index.js"
    assert worker_file.is_file(), "Cloudflare worker script must exist."
    worker_code = worker_file.read_text(encoding="utf-8")
    assert "openrouter/free" in worker_code, "Worker must route to latest free agentic models."
    assert "ADILIO FARIAS" in worker_code, "Worker must contain grounded RAG prompt."

