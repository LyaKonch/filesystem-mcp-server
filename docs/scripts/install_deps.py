"""Install runtime and optional development dependencies from `pyproject.toml`."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path


def main() -> int:
    """Install dependencies listed in project metadata.

    Returns:
        int: Process exit code.
    """
    parser = argparse.ArgumentParser(description="Install dependencies from pyproject.toml")
    parser.add_argument("--with-dev", action="store_true", help="Include dependency-groups.dev")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        print(f"pyproject.toml not found: {pyproject}")
        return 1

    with pyproject.open("rb") as file:
        data = tomllib.load(file)

    dependencies = list(data.get("project", {}).get("dependencies", []))
    if args.with_dev:
        dependencies.extend(data.get("dependency-groups", {}).get("dev", []))

    if not dependencies:
        print("No dependencies found to install")
        return 0

    subprocess.check_call([sys.executable, "-m", "pip", "install", *dependencies], cwd=project_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
