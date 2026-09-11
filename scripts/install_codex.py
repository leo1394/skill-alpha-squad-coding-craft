#!/usr/bin/env python3
"""Install the bundled skill and missing Codex agent roles for one user."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "alpha-squad-coding-craft"
SKILL_SOURCE = PROJECT_ROOT / "skills" / SKILL_NAME
AGENT_INSTALLER = SKILL_SOURCE / "scripts" / "install_codex_agents.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, help="Codex home directory")
    parser.add_argument(
        "--force-skill",
        action="store_true",
        help="Update files in an existing skill installation",
    )
    parser.add_argument(
        "--force-agents",
        action="store_true",
        help="Replace existing Codex role files",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    return parser.parse_args()


def resolve_codex_home(argument: Path | None) -> Path:
    configured = os.environ.get("CODEX_HOME") or "~/.codex"
    return (argument or Path(configured)).expanduser().resolve()


def install_skill(home: Path, *, force: bool, dry_run: bool) -> None:
    if not SKILL_SOURCE.is_dir():
        raise FileNotFoundError(f"bundled skill directory missing: {SKILL_SOURCE}")
    target = home / "skills" / SKILL_NAME
    if target.is_symlink():
        raise OSError(f"refusing to replace symlink: {target}")
    if target.exists() and not target.is_dir():
        raise OSError(f"skill target is not a directory: {target}")
    if target.exists() and not force:
        print(f"skip existing skill {target}")
        return
    action = "update" if target.exists() else "install"
    if dry_run:
        print(f"{action} skill {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SKILL_SOURCE, target, dirs_exist_ok=force)
    print(f"{action} skill {target}")


def install_agents(home: Path, *, force: bool, dry_run: bool) -> None:
    command = [
        sys.executable,
        str(AGENT_INSTALLER),
        "--codex-home",
        str(home),
    ]
    if force:
        command.append("--force")
    if dry_run:
        command.append("--dry-run")
    subprocess.run(command, check=True)


def main() -> int:
    arguments = parse_args()
    home = resolve_codex_home(arguments.codex_home)
    try:
        install_skill(
            home,
            force=arguments.force_skill,
            dry_run=arguments.dry_run,
        )
        install_agents(
            home,
            force=arguments.force_agents,
            dry_run=arguments.dry_run,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if not arguments.dry_run:
        print("Codex installation complete. Start a new session before using the skill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
