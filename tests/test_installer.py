from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import importlib.util
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (
    ROOT
    / "skills"
    / "alpha-squad-coding-craft"
    / "scripts"
    / "install_codex_agents.py"
)
ROLE_NAMES = {"explorer", "worker", "tester", "researcher", "reviewer"}


def load_installer_module():
    specification = importlib.util.spec_from_file_location(
        "install_codex_agents",
        INSTALLER,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class InstallerTest(unittest.TestCase):
    def run_installer(
        self,
        codex_home: Path,
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--codex-home",
                str(codex_home),
                *arguments,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_install_skip_dry_run_and_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            codex_home = base / "codex"

            first = self.run_installer(codex_home)
            self.assertEqual(first.returncode, 0, first.stderr)
            installed = {path.stem for path in (codex_home / "agents").glob("*.toml")}
            self.assertEqual(installed, ROLE_NAMES)

            explorer = codex_home / "agents" / "explorer.toml"
            explorer.write_text("local customization\n", encoding="utf-8")
            second = self.run_installer(codex_home)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(explorer.read_text(encoding="utf-8"), "local customization\n")
            self.assertEqual(second.stdout.count("skip existing"), len(ROLE_NAMES))

            dry_home = base / "dry-run"
            dry_run = self.run_installer(dry_home, "--dry-run")
            self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
            self.assertFalse(dry_home.exists())

            forced = self.run_installer(codex_home, "--force")
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertIn('name = "explorer"', explorer.read_text(encoding="utf-8"))

    def test_empty_codex_home_uses_user_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fake_user_home = Path(temporary_directory)
            environment = os.environ.copy()
            environment["HOME"] = str(fake_user_home)
            environment["USERPROFILE"] = str(fake_user_home)
            environment["CODEX_HOME"] = ""
            result = subprocess.run(
                [sys.executable, str(INSTALLER)],
                cwd=fake_user_home,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((fake_user_home / ".codex/agents/explorer.toml").is_file())
            self.assertFalse((fake_user_home / "agents").exists())

    def test_no_clobber_when_target_appears_during_install(self) -> None:
        installer = load_installer_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            source = base / "source.toml"
            target = base / "agents" / "worker.toml"
            source.write_text("template\n", encoding="utf-8")
            real_link = os.link

            def create_customization_then_link(temporary: Path, destination: Path) -> None:
                destination.write_text("new customization\n", encoding="utf-8")
                real_link(temporary, destination)

            with mock.patch.object(
                installer.os,
                "link",
                side_effect=create_customization_then_link,
            ):
                installed = installer.copy_atomic(source, target, replace=False)

            self.assertFalse(installed)
            self.assertEqual(target.read_text(encoding="utf-8"), "new customization\n")

    def test_interrupted_copy_leaves_target_recoverable(self) -> None:
        installer = load_installer_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            source = base / "source.toml"
            target = base / "agents" / "worker.toml"
            source.write_text("complete template\n", encoding="utf-8")

            with mock.patch.object(
                installer.shutil,
                "copyfileobj",
                side_effect=KeyboardInterrupt,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    installer.copy_atomic(source, target, replace=False)

            self.assertFalse(target.exists())
            orphan = target.parent / ".worker.toml.interrupted"
            orphan.write_text("partial temporary data\n", encoding="utf-8")
            self.assertTrue(installer.copy_atomic(source, target, replace=False))
            self.assertEqual(target.read_text(encoding="utf-8"), "complete template\n")


if __name__ == "__main__":
    unittest.main()
