"""Portfolio benchmark script."""
import os, shutil, subprocess, yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "benchmarks" / "workspaces" / "portfolio-masteradilio"
PRD_PATH = ROOT / "samples" / "e2e-portfolio-masteradilio" / "PRD.md"
FIXTURE_PATH = ROOT / "scripts" / "fixtures" / "portfolio_acceptance.py"

def setup_workspace():
    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=WORKSPACE, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Adilio Farias Portfolio Benchmark"], cwd=WORKSPACE, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "adiliobb@gmail.com"], cwd=WORKSPACE, check=True, capture_output=True)
    shutil.copy(PRD_PATH, WORKSPACE / "PRD.md")
    tests_dir = WORKSPACE / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE_PATH, tests_dir / "test_portfolio_acceptance.py")
    lf_dir = WORKSPACE / ".localforge"
    lf_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "version": 1,
        "project": {"name": "Portfolio Profissional - Adilio Farias"},
        "models": {
            "provider": "llamacpp",
            "base_url": "http://localhost:8080/v1",
            "default_model": "qwen3.8-27b",
            "fallback_models": ["qwen3.8-27b", "auto/best-free"],
            "fallback_routes": [{"provider": "omniroute", "base_url": "http://localhost:20128/v1", "model": "auto/best-free"}]
        },
        "chief_engineer": {
            "enabled": True,
            "provider": "llamacpp",
            "base_url": "http://localhost:8080/v1",
            "model": "qwen3.8-27b",
            "visual_model": "qwen3.8-27b",
            "fallback_routes": [{"provider": "omniroute", "base_url": "http://localhost:20128/v1", "model": "auto/best-free"}],
            "timeout": 120.0
        },
        "budgets": {
            "max_run_time": 1800.0,
            "max_task_duration": 300.0,
            "max_repair_attempts": 3,
            "max_diff_growth": 50000
        },
        "release": {
            "tester_command": "py -3.11 -m pytest tests/test_portfolio_acceptance.py -q"
        }
    }
    (lf_dir / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=WORKSPACE, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial portfolio benchmark baseline"], cwd=WORKSPACE, check=True, capture_output=True)
    print(f"Workspace initialized at {WORKSPACE}")

if __name__ == "__main__":
    setup_workspace()
