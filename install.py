#!/usr/bin/env python3
"""One-command installer for muse-bridge.

Creates a local virtualenv, installs the package (which pulls Playwright and
PyYAML from pyproject), installs the Chromium binary, and runs the self-check.
No shell magic, no global installs, no credentials touched.

Examples:
  python install.py
  python install.py --skip-browser
  python install.py --dry-run
  python install.py --no-venv --skip-deps --skip-browser --no-check
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def run(cmd: list[str], dry: bool) -> None:
    print("+ " + " ".join(cmd))
    if not dry:
        subprocess.run(cmd, check=True, cwd=str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Install muse-bridge into a local venv")
    ap.add_argument("--venv", default=".venv", help="virtualenv directory (default .venv)")
    ap.add_argument("--python", default=sys.executable, help="interpreter used to create the venv")
    ap.add_argument("--no-venv", action="store_true", help="use the current interpreter")
    ap.add_argument("--skip-deps", action="store_true", help="skip pip install/upgrade")
    ap.add_argument("--skip-browser", action="store_true", help="skip Playwright Chromium download")
    ap.add_argument("--no-check", action="store_true", help="skip run_me.py --check")
    ap.add_argument("--dry-run", action="store_true", help="print commands only")
    args = ap.parse_args()

    if args.no_venv:
        python = Path(sys.executable)
        print("using current interpreter:", python)
    else:
        venv_dir = Path(args.venv)
        if not venv_dir.is_absolute():
            venv_dir = ROOT / venv_dir
        python = venv_python(venv_dir)
        if not venv_dir.exists():
            run([args.python, "-m", "venv", str(venv_dir)], args.dry_run)
        elif not python.exists():
            print("venv exists but its python is missing:", python, file=sys.stderr)
            return 2
        print("venv:", venv_dir)

    if not args.skip_deps:
        run([str(python), "-m", "pip", "install", "--upgrade", "pip"], args.dry_run)
        run([str(python), "-m", "pip", "install", "-e", str(ROOT)], args.dry_run)

    if not args.skip_browser:
        run([str(python), "-m", "playwright", "install", "chromium"], args.dry_run)

    if not args.no_check:
        run([str(python), str(ROOT / "run_me.py"), "--check"], args.dry_run)

    if not args.dry_run:
        print("\nready. venv python:", python)
        print("next: python -m muse_bridge.cli login   (or accounts import an existing auth.json)")
        print("MCP:  point your client at  %s -X utf8 -m muse_bridge.mcp_server  with cwd=src" % python)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
