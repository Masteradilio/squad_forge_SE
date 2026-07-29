from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "command": command,
        "cwd": str(cwd) if cwd else None,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def _venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build, install, and smoke-test LocalForge package artifacts.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="localforge-package-smoke-") as tmp:
        tmp_path = Path(tmp)
        dist_dir = tmp_path / "dist"
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        commands: list[dict[str, object]] = []
        build = _run(
            [sys.executable, "-m", "build", "--sdist", "--wheel", "--outdir", str(dist_dir)],
            cwd=ROOT,
            env=env,
        )
        commands.append(build)
        if build["exit_code"] != 0:
            return _finish(commands, dist_dir, failed=True, output=args.output)

        wheels = sorted(dist_dir.glob("localforge_os-*.whl"))
        sdists = sorted(dist_dir.glob("localforge_os-*.tar.gz"))
        if len(wheels) != 1 or len(sdists) != 1:
            commands.append(
                {
                    "command": ["artifact-discovery"],
                    "cwd": str(dist_dir),
                    "exit_code": 1,
                    "stdout": json.dumps(
                        {
                            "wheels": [path.name for path in wheels],
                            "sdists": [path.name for path in sdists],
                        },
                        sort_keys=True,
                    ),
                    "stderr": "expected exactly one wheel and one sdist",
                }
            )
            return _finish(commands, dist_dir, failed=True, output=args.output)

        with zipfile.ZipFile(wheels[0]) as wheel_archive:
            packaged_tests = [
                name for name in wheel_archive.namelist() if name.startswith("tests/")
            ]
        if packaged_tests:
            commands.append(
                {
                    "command": ["wheel-content-check", wheels[0].name],
                    "cwd": str(dist_dir),
                    "exit_code": 1,
                    "stdout": json.dumps({"packaged_tests": packaged_tests[:20]}, sort_keys=True),
                    "stderr": "wheel must not include backend test modules",
                }
            )
            return _finish(commands, dist_dir, failed=True, output=args.output)

        venv_dir = tmp_path / "install-env"
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(venv_dir)
        python = _venv_python(venv_dir)

        install = _run([str(python), "-m", "pip", "install", str(wheels[0])], env=env)
        commands.append(install)
        if install["exit_code"] != 0:
            return _finish(commands, dist_dir, failed=True, output=args.output)

        smoke = _run(
            [
                str(python),
                "-c",
                "import localforge; from localforge.version import VERSION; print(localforge.__version__); assert VERSION == localforge.__version__",
            ],
            cwd=tmp_path,
            env=env,
        )
        commands.append(smoke)

        cli = _run([str(python), "-m", "localforge.cli.main", "--version"], cwd=tmp_path, env=env)
        commands.append(cli)

        help_result = _run([str(python), "-m", "localforge.cli.main", "--help"], cwd=tmp_path, env=env)
        commands.append(help_result)

        failed = any(command["exit_code"] != 0 for command in commands)
        return _finish(commands, dist_dir, failed=failed, output=args.output)


def _finish(commands: list[dict[str, object]], dist_dir: Path, *, failed: bool, output: str | None) -> int:
    artifacts = []
    if dist_dir.exists():
        artifacts = sorted(path.name for path in dist_dir.iterdir() if path.is_file())
    payload = {
        "schema_version": "localforge.v6_2.clean_package_install.v1",
        "platform": sys.platform,
        "python": sys.version,
        "artifacts": artifacts,
        "commands": commands,
        "passed": not failed,
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
