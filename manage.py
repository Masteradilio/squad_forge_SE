#!/usr/bin/env python3
import os
import sys
import subprocess
import platform

# Pre-determine OS paths
IS_WINDOWS = platform.system() == "Windows"
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_venv_bin():
    if IS_WINDOWS:
        return os.path.join(ROOT_DIR, ".venv", "Scripts")
    return os.path.join(ROOT_DIR, ".venv", "bin")

def get_venv_python():
    ext = ".exe" if IS_WINDOWS else ""
    return os.path.join(get_venv_bin(), f"python{ext}")

def get_venv_pip():
    ext = ".exe" if IS_WINDOWS else ""
    return os.path.join(get_venv_bin(), f"pip{ext}")

def run_cmd(cmd, cwd=ROOT_DIR, env_vars=None):
    """Run a shell command and stream output, exiting on failure."""
    print(f"\n[Command] Running: {' '.join(cmd)} in {cwd}")
    
    current_env = os.environ.copy()
    if env_vars:
        current_env.update(env_vars)
        
    try:
        res = subprocess.run(cmd, cwd=cwd, env=current_env)
        if res.returncode != 0:
            print(f"[Error] Command failed with exit code: {res.returncode}")
            sys.exit(res.returncode)
    except FileNotFoundError as e:
        print(f"[Error] Executable not found: {e}")
        sys.exit(1)

def setup_backend():
    print("=== Setting up Backend virtual environment and dependencies ===")
    venv_dir = os.path.join(ROOT_DIR, ".venv")
    
    if not os.path.exists(venv_dir):
        print(f"Creating virtual environment in: {venv_dir}")
        run_cmd([sys.executable, "-m", "venv", ".venv"])
    else:
        print("Virtual environment (.venv) already exists.")
        
    pip_path = get_venv_pip()
    
    # Upgrade pip
    run_cmd([pip_path, "install", "--upgrade", "pip"])
    
    # Install the package and contributor tools through the canonical metadata.
    run_cmd([pip_path, "install", "-e", ".[dev]"])
        
    # Initialize workspace using localforge init
    python_path = get_venv_python()
    run_cmd([python_path, "-m", "localforge.cli.main", "init"])
    
    print("\n[Success] Backend setup completed!")

def setup_frontend():
    print("=== Setting up Frontend dependencies ===")
    frontend_dir = os.path.join(ROOT_DIR, "frontend")
    
    # Check if npm is installed
    npm_cmd = "npm.cmd" if IS_WINDOWS else "npm"
    run_cmd([npm_cmd, "install"], cwd=frontend_dir)
    
    print("\n[Success] Frontend setup completed!")

def run_backend():
    print("=== Starting LocalForge OS API Server ===")
    python_path = get_venv_python()
    
    if not os.path.exists(python_path):
        print("[Error] Virtual environment not found. Please run 'python manage.py setup-backend' first.")
        sys.exit(1)
        
    env = {"PYTHONPATH": os.path.join(ROOT_DIR, "backend")}
    cmd = [
        python_path, "-m", "uvicorn", 
        "localforge.api.app:create_app", 
        "--factory", 
        "--host", "127.0.0.1", 
        "--port", "8000", 
        "--reload"
    ]
    run_cmd(cmd, env_vars=env)

def run_frontend():
    print("=== Starting LocalForge OS Frontend Dev Server ===")
    frontend_dir = os.path.join(ROOT_DIR, "frontend")
    npm_cmd = "npm.cmd" if IS_WINDOWS else "npm"
    run_cmd([npm_cmd, "run", "dev"], cwd=frontend_dir)

def run_tests():
    print("=== Running Backend Pytest suite ===")
    python_path = get_venv_python()
    
    if not os.path.exists(python_path):
        print("[Error] Virtual environment not found. Please run 'python manage.py setup-backend' first.")
        sys.exit(1)
        
    env = {"PYTHONPATH": os.path.join(ROOT_DIR, "backend")}
    run_cmd([python_path, "-m", "pytest", "backend/tests/"], env_vars=env)

def run_lint():
    print("=== Running Linters ===")
    python_path = get_venv_python()
    
    # Backend Ruff Check
    if os.path.exists(python_path):
        print("\n--- Ruff checks (Backend) ---")
        env = {"PYTHONPATH": os.path.join(ROOT_DIR, "backend")}
        # We don't fail immediately on backend lint so we can also check frontend
        try:
            subprocess.run([python_path, "-m", "ruff", "check", "backend"], cwd=ROOT_DIR, env=os.environ.copy() | env, check=True)
            print("Ruff checks passed!")
        except subprocess.CalledProcessError as e:
            print(f"[Warning] Ruff check failed: {e}")
    else:
        print("[Warning] Virtual environment not found. Skipping backend Ruff checks.")
        
    # Frontend Lint Check
    print("\n--- Eslint checks (Frontend) ---")
    frontend_dir = os.path.join(ROOT_DIR, "frontend")
    npm_cmd = "npm.cmd" if IS_WINDOWS else "npm"
    try:
        subprocess.run([npm_cmd, "run", "lint"], cwd=frontend_dir, check=True, shell=IS_WINDOWS)
        print("Eslint checks passed!")
    except subprocess.CalledProcessError as e:
        print(f"[Warning] Frontend lint failed: {e}")
        
    print("\nLinting checks finished.")

def print_help():
    print("""LocalForge OS Developer Utility

Usage:
  python manage.py <command>

Commands:
  setup-backend   Create virtualenv, install packages, and initialize workspace
  setup-frontend  Install node modules for the frontend SPA
  run-backend     Run the FastAPI server using Uvicorn
  run-frontend    Run the React Vite dev server
  run-tests       Execute backend tests with pytest
  lint            Run backend Ruff checks and frontend Eslint
""")

def main():
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)
        
    cmd = sys.argv[1]
    
    commands = {
        "setup-backend": setup_backend,
        "setup-frontend": setup_frontend,
        "run-backend": run_backend,
        "run-frontend": run_frontend,
        "run-tests": run_tests,
        "lint": run_lint
    }
    
    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
