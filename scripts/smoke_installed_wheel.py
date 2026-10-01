"""Exercise one built wheel in a fresh environment outside the source checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOAL_ID = "github-authority-audit-synthetic"


def _run(
    command: list[str], *, cwd: Path, env: dict[str, str], expected: int = 0
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if result.returncode != expected:
        raise AssertionError(
            f"expected exit {expected}, got {result.returncode}: {' '.join(command)}\n"
            f"stdout:\n{result.stdout[-3000:]}\nstderr:\n{result.stderr[-3000:]}"
        )
    return result


def _wheel(path: Path) -> Path:
    wheels = sorted(path.glob("loop_engineering-*.whl")) if path.is_dir() else [path]
    if len(wheels) != 1 or not wheels[0].is_file():
        raise ValueError(f"expected exactly one built loop-engineering wheel at {path}")
    return wheels[0].resolve()


def smoke(wheel: Path, *, inherit_dependencies: bool = False) -> None:
    with tempfile.TemporaryDirectory(prefix="loop-installed-wheel-") as folder:
        scratch = Path(folder)
        environment = scratch / "venv"
        sandbox = scratch / "outside-checkout"
        sandbox.mkdir()
        venv.EnvBuilder(with_pip=True, system_site_packages=inherit_dependencies).create(
            environment
        )
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        clean_env = dict(os.environ)
        for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
            clean_env.pop(name, None)
        clean_env["PYTHONDONTWRITEBYTECODE"] = "1"
        install = [str(python), "-m", "pip", "install", "--disable-pip-version-check"]
        if inherit_dependencies:
            install += ["--no-index", "--no-deps"]
        _run([*install, str(wheel)], cwd=sandbox, env=clean_env)

        input_root = sandbox / "input"
        input_root.mkdir()
        goal = input_root / "goal.synthetic.yaml"
        subjects = input_root / "subjects.synthetic.yaml"
        fixtures = input_root / "github"
        shutil.copy2(ROOT / "examples" / goal.name, goal)
        shutil.copy2(ROOT / "examples" / subjects.name, subjects)
        shutil.copytree(ROOT / "evals" / "fixtures" / "github", fixtures)

        package_probe = """
import hashlib, json, loop_engineering
from importlib.resources import files
schemas = files('loop_engineering').joinpath('schemas')
print(json.dumps({
    'package': loop_engineering.__file__,
    'schemas': {item.name: hashlib.sha256(item.read_bytes()).hexdigest()
                for item in schemas.iterdir() if item.name.endswith('.json')},
}))
"""
        probe = _run([str(python), "-c", package_probe], cwd=sandbox, env=clean_env)
        loaded = json.loads(probe.stdout)
        package = Path(loaded["package"]).resolve()
        assert environment.resolve() in package.parents, package
        expected_schemas = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (ROOT / "src" / "loop_engineering" / "schemas").glob("*.json")
        }
        assert loaded["schemas"] == expected_schemas, "built wheel schema files differ"

        entrypoint = environment / (
            "Scripts/loop-engineering.exe" if os.name == "nt" else "bin/loop-engineering"
        )
        assert entrypoint.is_file(), "built wheel did not install its CLI entrypoint"
        cli = [str(entrypoint)]
        _run([*cli, "--help"], cwd=sandbox, env=clean_env)
        _run([*cli, "init", str(goal)], cwd=sandbox, env=clean_env)
        inputs = ["--subjects", str(subjects), "--fixtures", str(fixtures)]
        first = _run(
            [*cli, "audit-github", "--goal-file", str(goal), *inputs],
            cwd=sandbox,
            env=clean_env,
        )
        assert "GOAL_MATCH" in first.stdout
        run_root = sandbox / "runs" / GOAL_ID
        first_run = next(run_root.iterdir())
        _run([*cli, "verify", str(first_run)], cwd=sandbox, env=clean_env)
        report = _run([*cli, "report", str(first_run)], cwd=sandbox, env=clean_env)
        assert "# Accuracy Evidence" in report.stdout

        interrupted = _run(
            [*cli, "audit-github", "--goal-file", str(goal), *inputs, "--interrupt-after", "2"],
            cwd=sandbox,
            env=clean_env,
            expected=2,
        )
        assert "simulated crash" in interrupted.stderr
        second_run = next(path for path in run_root.iterdir() if path != first_run)
        _run([*cli, "resume", str(second_run), *inputs], cwd=sandbox, env=clean_env)
        _run([*cli, "verify", str(second_run)], cwd=sandbox, env=clean_env)
        resumed_report = _run([*cli, "report", str(second_run)], cwd=sandbox, env=clean_env)
        assert "# Accuracy Evidence" in resumed_report.stdout
        print(f"installed-wheel smoke passed: {wheel.name}; package={package}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, help="exact built wheel or directory containing one")
    parser.add_argument(
        "--inherit-dependencies",
        action="store_true",
        help="offline local fallback; CI uses isolated dependency installation",
    )
    args = parser.parse_args()
    try:
        smoke(_wheel(args.wheel), inherit_dependencies=args.inherit_dependencies)
    except (AssertionError, ValueError) as exc:
        print(f"installed-wheel smoke failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
