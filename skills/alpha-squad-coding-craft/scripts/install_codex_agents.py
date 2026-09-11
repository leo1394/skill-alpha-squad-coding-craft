#!/usr/bin/env python3
"""Install bundled Codex role files without overwriting local customizations."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROLE_NAMES = ("explorer", "worker", "tester", "researcher", "reviewer")
SOURCE_DIR = Path(__file__).resolve().parent.parent / "assets" / "codex-agents"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, help="Codex home directory")
    parser.add_argument("--force", action="store_true", help="Replace existing role files")
    parser.add_argument("--dry-run", action="store_true", help="Report actions without writing")
    return parser.parse_args()


def copy_atomic(source: Path, target: Path, *, replace: bool) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as destination, source.open("rb") as origin:
            shutil.copyfileobj(origin, destination)
            destination.flush()
            os.fsync(destination.fileno())
        if replace:
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target)
            except FileExistsError:
                return False
        return True
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    configured_home = os.environ.get("CODEX_HOME") or "~/.codex"
    home = (args.codex_home or Path(configured_home)).expanduser()
    target_dir = home / "agents"
    try:
        if not SOURCE_DIR.is_dir():
            raise FileNotFoundError(f"bundled role directory missing: {SOURCE_DIR}")
        if target_dir.exists() and not target_dir.is_dir():
            raise OSError(f"agent target is not a directory: {target_dir}")
        actions = []
        for role in ROLE_NAMES:
            source = SOURCE_DIR / f"{role}.toml"
            target = target_dir / source.name
            if not source.is_file():
                raise FileNotFoundError(f"bundled role file missing: {source}")
            if target.is_symlink():
                raise OSError(f"refusing to write through symlink: {target}")
            if target.exists() and not target.is_file():
                raise OSError(f"agent target is not a regular file: {target}")
            if target.exists() and not args.force:
                actions.append(("skip", target))
            else:
                actions.append(("replace" if target.exists() else "install", target, source))
        for action in actions:
            if action[0] == "skip":
                print(f"skip existing {action[1]}")
            else:
                if args.dry_run:
                    print(f"{action[0]} {action[1]}")
                else:
                    installed = copy_atomic(
                        action[2],
                        action[1],
                        replace=action[0] == "replace",
                    )
                    if installed:
                        print(f"{action[0]} {action[1]}")
                    else:
                        print(f"skip concurrently created {action[1]}")
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
